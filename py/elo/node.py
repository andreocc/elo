"""Elo Node — nó P2P da malha Elo. Um processo, uma porta, uma chave.

Uso:
    node = Node("meu-agente", port=7878)
    await node.connect()
    await node.register(agents=["analyst"], tools=["web-search"])

    @node.on_task
    async def handle(task):
        return {"result": "ok"}

    await node.run()
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
import uuid
from collections.abc import Callable, Awaitable
from pathlib import Path
from typing import Any

from elo.transport import (
    TCPManager,
    InterestTable,
    LocalTracker,
    hello_msg,
    hello_ack_msg,
    query_msg,
    query_resp_msg,
    interest_update_msg,
    task_msg as p2p_task_msg,
    result_msg,
    MessageType,
    DiscoveryManager,
)
import os
from elo.security import EphemeralIdentity
from elo.types import Capabilities, Result, Task
from elo.pending_queue import PendingQueue, PendingTask

logger = logging.getLogger("elo")

DEFAULT_DATA_DIR = Path.home() / ".elo"


def save_last_peers(peers: list[str]) -> None:
    try:
        path = DEFAULT_DATA_DIR / "last_peer"
        path.parent.mkdir(parents=True, exist_ok=True)
        # Store up to 10 unique peers
        existing = load_last_peers()
        combined = list(dict.fromkeys(peers + existing))[:10]
        path.write_text("\n".join(combined), encoding="utf-8")
    except Exception:
        pass


def load_last_peers() -> list[str]:
    try:
        path = DEFAULT_DATA_DIR / "last_peer"
        if path.exists():
            return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except Exception:
        pass
    return []


class Node:
    """Nó P2P da malha Elo.

    Um processo. Uma porta TCP. Uma chave ed25519.
    Zero infraestrutura externa.
    """

    def __init__(
        self,
        name: str,
        *,
        port: int = 7878,
        peers: list[str] | None = None,
        tracker: str = "public",
        allowlist: list[str] | None = None,
        version: str = "0.5.1",
        identity: EphemeralIdentity | None = None,
        verify_peers: bool = True,
        heartbeat_interval_s: int = 30,
        labels: dict[str, str] | None = None,
    ):
        self._name = name
        self._version = version
        self._port = port
        self._initial_peers = peers or []
        self._heartbeat_interval = heartbeat_interval_s
        self._labels = labels or {}
        self._verify_peers = verify_peers

        # Identidade
        self._identity = identity or EphemeralIdentity()
        self._node_id = self._identity.node_id

        # Fallback Queue
        self._pending_queue = PendingQueue(self._node_id)
        self._flushing_pending = False

        # Reconnection State
        self._reconnect_backoff: dict[str, int] = {}
        self._reconnecting_peers: set[str] = set()

        # Monitoring State
        self._started_at = time.time()
        self._last_heartbeat_received = 0.0

        # Tracker host & visibility
        tracker_host = os.environ.get("ELO_TRACKER_HOST", "tracker.elo.sh:7878")
        visibility = "public"
        if tracker in ("public", "private"):
            visibility = tracker
        else:
            tracker_host = tracker
            visibility = "public"
        self._tracker_host = tracker_host

        # Transporte
        self._tcp = TCPManager(self._node_id, port=port)

        # Roteamento
        self._routing = InterestTable()
        self._tracker = LocalTracker(visibility=visibility)
        if allowlist:
            for nid in allowlist:
                self._tracker.allow_peer(nid)

        # Estado
        self._task_handler: Callable[[Task], Awaitable[dict[str, Any]]] | None = None
        self._shutdown_event = asyncio.Event()
        self._pending_results: dict[str, asyncio.Future] = {}
        self._pending_queries: dict[str, tuple[list[dict[str, Any]], asyncio.Event, float]] = {}

        # Cache de pubkeys para verificação de assinatura
        self._pubkey_cache: dict[str, tuple[Any, float]] = {}
        self._cache_ttl_s = heartbeat_interval_s * 5

        # Rate limiting
        self._msg_count: dict[str, tuple[int, float]] = {}  # peer_addr → (count, window_start)
        self._hello_count: dict[str, float] = {}             # peer_addr → last_hello_timestamp

        # Cache de query_ids para prevenir broadcast loop
        self._seen_queries: dict[str, float] = {}
        self._seen_query_ttl = 60  # segundos

    # ── propriedades ──────────────────────────────────────────

    @property
    def node_id(self) -> str:
        return self._node_id

    @property
    def connected(self) -> bool:
        return self._tcp._server is not None

    @property
    def identity(self) -> EphemeralIdentity:
        return self._identity

    @property
    def port(self) -> int:
        return self._tcp.port

    @property
    def peer_count(self) -> int:
        return self._tcp.peer_count

    @property
    def tracker_visibility(self) -> str:
        return self._tracker.visibility

    # ── observabilidade mínima ─────────────────────────────────

    def metrics(self) -> dict[str, Any]:
        return {
            "node_id": self._node_id[:12],
            "port": self._port,
            "peers_connected": self._tcp.peer_count,
            "peer_addresses": self._tcp.peer_addresses,
            "tracker": self._tracker.visibility,
            "caps": len(self._routing.local_caps),
        }

    # ── ciclo de vida ─────────────────────────────────────────

    async def connect(self) -> None:
        if self.connected:
            return

        actual_port = await self._tcp.start()
        self._port = actual_port
        self._tcp.on_message(self._handle_message)

        # Build hello payload
        hello = self._build_hello_msg()

        # Start DiscoveryManager
        self._discovery = DiscoveryManager(
            self._node_id,
            actual_port,
            self._on_discovered_peer
        )
        await self._discovery.start()

        # Conecta a peers manuais
        if self._initial_peers:
            for addr in self._initial_peers:
                await self._tcp.connect_to_peer(addr, hello_payload=hello)
        else:
            # Zero-Config Bootstrap
            connected_to_tracker = False
            if self._tracker_host:
                try:
                    logger.info("[node] attempting bootstrap with tracker: %s", self._tracker_host)
                    res = await asyncio.wait_for(
                        self._tcp.connect_to_peer(self._tracker_host, hello_payload=hello),
                        timeout=5.0
                    )
                    if res:
                        connected_to_tracker = True
                        logger.info("[node] bootstrap connected to tracker: %s", self._tracker_host)
                except Exception as e:
                    logger.debug("[node] bootstrap tracker connection failed: %s", e)

            if not connected_to_tracker:
                last_peers = load_last_peers()
                if last_peers:
                    logger.info("[node] attempting bootstrap with cached last peers: %s", last_peers)
                    for addr in last_peers:
                        try:
                            await asyncio.wait_for(
                                self._tcp.connect_to_peer(addr, hello_payload=hello),
                                timeout=3.0
                            )
                        except Exception as e:
                            logger.debug("[node] failed to connect to cached peer %s: %s", addr, e)

            # Send multicast announcement
            await self._discovery.announce()

        logger.info("[elo] connected | node=%s id=%s port=%d",
                     self._name, self._node_id[:12], actual_port)

    async def disconnect(self) -> None:
        self._shutdown_event.set()
        if hasattr(self, "_discovery") and self._discovery:
            await self._discovery.stop()
        await self._tcp.stop()
        logger.info("[elo] disconnected | node=%s", self._name)

    # ── registro ──────────────────────────────────────────────

    async def register(
        self,
        *,
        agents: list[str] | None = None,
        models: list[str] | None = None,
        tools: list[str] | None = None,
        agent_details: list[dict[str, str]] | None = None,
        model_details: list[dict[str, str]] | None = None,
        tool_details: list[dict[str, str]] | None = None,
    ) -> None:
        agent_caps = agent_details or [{"name": a} for a in (agents or [])]
        model_caps = model_details or [{"name": m} for m in (models or [])]
        tool_caps = tool_details or [{"name": t} for t in (tools or [])]

        if not any(t.get("name") == "health" for t in tool_caps):
            tool_caps.append({"name": "health", "description": "Built-in health check"})

        self._tracker.register(agents=agent_caps, models=model_caps, tools=tool_caps)
        self._routing.set_local_caps(self._tracker.caps)

        interests = [a.get("name", "") for a in agent_caps]
        interests += [t.get("name", "") for t in tool_caps]
        self._tracker.set_interests(interests)
        self._routing.set_local_interests(interests)

        update = interest_update_msg(interests)
        await self._tcp.broadcast(update)

        logger.info("[elo] registered | agents=%d models=%d tools=%d",
                     len(agent_caps), len(model_caps), len(tool_caps))

    # ── handlers ───────────────────────────────────────────────

    def on_task(self, fn: Callable[[Task], Awaitable[dict[str, Any]]]):
        self._task_handler = fn
        return fn

    # ── mensagens ──────────────────────────────────────────────

    async def send_task(self, target_node: str, capability: str,
                        payload: dict[str, Any], *, ttl_s: int = 60,
                        _bypass_queue: bool = False) -> Result:
        """Envia task e aguarda resultado. Descobre peer se target vazio."""
        if not self.connected:
            raise RuntimeError("Node not connected")

        task_id = str(uuid.uuid4())
        task_dict = p2p_task_msg(task_id, target_node, self._node_id, capability, payload)
        task_dict.pop("signature", None)
        task_dict["signature"] = self._identity.sign(task_dict)

        # Tenta encontrar peer — matcha node_id contra addresses no formato "prefix@ip:port"
        peer = None
        result = None
        if target_node:
            for addr in self._tcp.peer_addresses:
                if addr.startswith(target_node[:12] + "@"):
                    peer = addr
                    break
            if not peer:
                # Bug fix: target_node especificado mas offline —
                # NÃO fazer find_peer_for(capability) que acharia o tracker.
                # Vai direto pra relay-via-tracker.
                result = await self.send_task_via_tracker(
                    "", target_node, capability, payload, ttl_s=ttl_s
                )
        else:
            peer = self._routing.find_peer_for(capability)
            if not peer:
                peer = await self._query_capability(capability, ttl=5, timeout=5)

        if not result:
            if peer:
                try:
                    await self._tcp.send_to(peer, task_dict)
                    result = await self._wait_for_result(task_id, peer)
                except Exception as e:
                    result = Result.make_error(task_id, "SEND_ERROR", str(e))
            else:
                result = Result.make_error(task_id, "NO_PEER", f"No peer for: {capability}")

        if result.status == "error" and not _bypass_queue:
            self._pending_queue.enqueue(task_id, target_node, capability, payload, ttl_s)
            return Result.make_error(task_id, "QUEUED", "Target offline, task queued for retry")

        return result

    async def send_task_async(self, target_node: str, capability: str,
                              payload: dict[str, Any]) -> str:
        """Envia task sem esperar resultado. Retorna task_id."""
        if not self.connected:
            raise RuntimeError("Node not connected")

        task_id = str(uuid.uuid4())
        task_dict = p2p_task_msg(task_id, target_node, self._node_id, capability, payload)
        task_dict.pop("signature", None)
        task_dict["signature"] = self._identity.sign(task_dict)

        peer = target_node or self._routing.find_peer_for(capability)
        if peer:
            try:
                await self._tcp.send_to(peer, task_dict)
            except Exception:
                pass
        else:
            await self._tcp.broadcast(task_dict)
        return task_id

    async def publish_event(self, event_type: str, target_node: str = "",
                            data: dict[str, Any] | None = None) -> None:
        if not self.connected:
            raise RuntimeError("Node not connected")
        event = {
            "type": MessageType.EVENT, "event_type": event_type,
            "data": data or {}, "id": str(uuid.uuid4()),
            "protocol": "elo.v1", "timestamp": int(time.time()),
        }
        if target_node and target_node in self._tcp.peer_addresses:
            await self._tcp.send_to(target_node, event)
        else:
            await self._tcp.broadcast(event)

    # ── descoberta ─────────────────────────────────────────────

    async def get_known_peers_local(self) -> list[dict[str, Any]]:
        """Return all locally-known peers with capabilities (no network discovery).

        Merges data from TCP connections (live) and InterestTable (registered).
        Does NOT perform any network queries — only returns what's already known.
        """
        result: dict[str, dict[str, Any]] = {}

        # From TCP connections — live peers
        for addr in self._tcp.peer_addresses:
            result[addr] = {"addr": addr, "connected": True, "caps": [], "via": "tcp"}

        # From InterestTable — peers that completed HELLO handshake
        for addr in self._routing.known_peers:
            caps = list(self._routing.get_peer_caps(addr).get("caps", set()))
            if addr in result:
                result[addr]["caps"] = caps
                result[addr]["via"] = "both"
            else:
                result[addr] = {"addr": addr, "connected": False, "caps": caps, "via": "routing"}

        return list(result.values())

    # Alias de compatibilidade — o método anterior chamava-se discover_peers()
    async def discover_peers(self) -> list[dict[str, Any]]:
        """[DEPRECATED] Use get_known_peers_local() ou discover_peers_network().

        Este método apenas consolida peers localmente conhecidos (TCP + InterestTable).
        Não faz descoberta ativa de rede. Prefira discover_peers_network() para
        descoberta via broadcast, ou get_known_peers() para peers com handshake completo.
        """
        return await self.get_known_peers_local()

    async def discover_peers_network(self, timeout: float = 5.0) -> list[dict[str, Any]]:
        """Discover peers on the network via QUERY broadcast.

        Envia QUERY com capability vazia e agrega todas as respostas
        dentro do timeout. Modelo BitTorrent: o tracker retorna todos
        os peers conhecidos, não só quem matcha a capability.
        """
        query_id = str(uuid.uuid4())[:8]
        collected: list[dict[str, Any]] = []
        event = asyncio.Event()
        self._pending_queries[query_id] = (collected, event, time.time())
        discovered: dict[str, dict[str, Any]] = {}

        # Broadcast QUERY for any capability
        await self._tcp.broadcast(query_msg("", query_id, ttl=3, origin=self._node_id))

        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass
        finally:
            self._pending_queries.pop(query_id, None)

        # Merge collected peers from all responses
        known_addrs: set[str] = set()
        for entry in collected:
            addr = entry.get("addr", "")
            if addr and addr not in discovered:
                discovered[addr] = {
                    "addr": addr,
                    "node_id": entry.get("node_id", ""),
                    "caps": entry.get("caps", []),
                    "connected": False,
                    "via": "network",
                }
                known_addrs.add(addr)

        # Merge with locally known peers
        local = await self.get_known_peers_local()
        for entry in local:
            addr = entry["addr"]
            if addr not in discovered:
                discovered[addr] = entry
            else:
                discovered[addr].update(entry)

        return list(discovered.values())

    def get_known_peers(self) -> list[dict[str, Any]]:
        """Return peers registered in InterestTable (completed HELLO handshake).

        More reliable than discover_peers() — only includes peers that
        completed the full handshake (HELLO + HELLO_ACK).
        Meant for tracker/discovery use cases.
        """
        result = []
        for addr in self._routing.known_peers:
            info = self._routing.get_peer_caps(addr)
            node_id_prefix = addr.split("@")[0] if "@" in addr else ""
            result.append({
                "addr": addr,
                "node_id": node_id_prefix,
                "caps": list(info.get("caps", set())),
                "interests": list(info.get("interests", set())),
            })
        return result

    # ── run loop ──────────────────────────────────────────────

    async def run(self) -> None:
        if not self.connected:
            raise RuntimeError("Node not connected — call connect() first")

        heartbeat_task = asyncio.create_task(self._tcp.start_heartbeat())
        await self.publish_event("node.online")

        logger.info("[elo] running | node=%s (%s) port=%d peers=%d",
                     self._name, self._node_id[:12], self._port, self._tcp.peer_count)

        # Run periodic tasks (e.g. flush pending fallback queue every 30s)
        while not self._shutdown_event.is_set():
            await self._flush_pending()
            try:
                await asyncio.wait_for(self._shutdown_event.wait(), timeout=30.0)
            except asyncio.TimeoutError:
                pass

        heartbeat_task.cancel()

    # ── message dispatcher ────────────────────────────────────

    async def _handle_message(self, peer_addr: str, msg: dict[str, Any]) -> None:
        msg_type = msg.get("type", "")

        # ── Rate limiting ───────────────────────────────────────
        now = time.monotonic()
        # HELLO: max 1 per minute per peer
        if msg_type == MessageType.HELLO:
            last_hello = self._hello_count.get(peer_addr, 0.0)
            if now - last_hello < 60:
                logger.warning("[elo] rate limit: HELLO flood from %s", peer_addr[:20])
                return
            self._hello_count[peer_addr] = now

        # General: max 100 messages per 60s window per peer
        count, win_start = self._msg_count.get(peer_addr, (0, now))
        if now - win_start > 60:
            count, win_start = 0, now
        count += 1
        self._msg_count[peer_addr] = (count, win_start)
        
        # BYE sempre passa — mesmo com rate limit, para não acumular stale peers
        if msg_type == MessageType.BYE:
            await self._on_bye(peer_addr, msg)
            return
        
        if count > 100:
            logger.warning("[elo] rate limit: %d msgs in 60s from %s — dropping", count, peer_addr[:20])
            return
        # ── Fim rate limiting ───────────────────────────────────

        if msg_type == MessageType.HELLO:
            await self._on_hello(peer_addr, msg)
        elif msg_type == MessageType.HELLO_ACK:
            await self._on_hello(peer_addr, msg)
            # Bug 1: Se HELLO_ACK contém known_peers, conectar-se a eles
            known_peers = msg.get("known_peers")
            if known_peers:
                hello = hello_msg(self._node_id, self._tracker.get_public_caps(),
                                  list(self._routing.local_interests),
                                  self._tracker.visibility, self._version)
                for peer_info in known_peers:
                    addr = peer_info.get("addr", "")
                    if addr and addr != peer_addr and addr not in self._tcp.peer_addresses:
                        asyncio.create_task(
                            self._tcp.connect_to_peer(addr, hello_payload=hello)
                        )
        elif msg_type == MessageType.QUERY:
            await self._on_query(peer_addr, msg)
        elif msg_type == MessageType.QUERY_RESP:
            await self._on_query_resp(peer_addr, msg)
        elif msg_type == MessageType.INTEREST_UPDATE:
            await self._on_interest_update(peer_addr, msg)
        elif msg_type == MessageType.TASK:
            await self._on_task(peer_addr, msg)
        elif msg_type == MessageType.RESULT:
            await self._on_result(peer_addr, msg)
        elif msg_type == MessageType.HEARTBEAT:
            self._last_heartbeat_received = time.time()

    # ── protocol handlers ─────────────────────────────────────

    async def _on_hello(self, peer_addr: str, msg: dict) -> None:
        node_id = msg.get("node_id", "")
        caps = msg.get("caps", {})
        interests = msg.get("interests", [])
        self._routing.register_peer(peer_addr, caps, interests)

        # Se for tracker (public/private), inclui peers conhecidos no ACK
        # Exclui o próprio peer que está conectando — senão ele tenta
        # conectar a si mesmo via known_peers.
        known_peers = None
        if msg.get("type") == MessageType.HELLO:
            if self._tracker.visibility in ("public", "private"):
                all_peers = self.get_known_peers()
                known_peers = [p for p in all_peers if p.get("addr", "") != peer_addr]

            ack = hello_ack_msg(self._node_id, self._tracker.get_caps_for_peer(node_id),
                                list(self._routing.local_interests), self._tracker.visibility,
                                known_peers=known_peers)
            try:
                await self._tcp.send_to(peer_addr, ack)
            except Exception:
                pass

        # Save peer to last known peers cache
        raw_addr = peer_addr.split("@")[-1] if "@" in peer_addr else peer_addr
        if ":" in raw_addr:
            save_last_peers([raw_addr])

        asyncio.create_task(self._flush_pending())

    async def _on_query(self, peer_addr: str, msg: dict) -> None:
        capability = msg.get("capability", "")
        query_id = msg.get("id", "")
        ttl = msg.get("ttl", 5)
        origin = msg.get("origin", "")

        # Previne broadcast loop: não reencaminha se origin == self
        if origin and origin == self._node_id:
            return

        # Previne duplicatas: cache de query_ids recentes
        now = time.time()
        # Limpa entradas expiradas
        expired = [qid for qid, ts in self._seen_queries.items() if now - ts > self._seen_query_ttl]
        for qid in expired:
            self._seen_queries.pop(qid, None)
        if query_id in self._seen_queries:
            return
        self._seen_queries[query_id] = now

        nodes: list[dict[str, Any]] = []

        # Modelo BitTorrent: tracker retorna SEMPRE todos os peers conhecidos,
        # não só quem matcha a capability. Isso permite que qualquer nó
        # descubra a mesh completa com discover_peers_network().
        for addr in self._routing.known_peers:
            info = self._routing.get_peer_caps(addr)
            if addr != peer_addr:
                node_id_prefix = addr.split("@")[0] if "@" in addr else ""
                nodes.append({
                    "addr": addr,
                    "node_id": node_id_prefix,
                    "caps": list(info.get("caps", set())),
                })

        if self._tracker.has_capability(capability):
            # Usa peer_addr (addr real do TCP) em vez de localhost — necessário para WAN/Tailscale
            nodes.append({"node_id": self._node_id[:12], "addr": peer_addr})

        if nodes:
            try:
                await self._tcp.send_to(peer_addr, query_resp_msg(query_id, nodes))
            except Exception:
                pass
        elif ttl > 1:
            # Propaga origin: usa a existente ou define self como origin
            origin = origin or self._node_id
            await self._tcp.broadcast(query_msg(capability, query_id, ttl=ttl - 1, origin=origin), exclude={peer_addr})

    async def _on_query_resp(self, peer_addr: str, msg: dict) -> None:
        query_id = msg.get("id", "")
        if query_id in self._pending_queries:
            collected, event, _ts = self._pending_queries[query_id]
            nodes = msg.get("nodes", [])
            if nodes:
                collected.extend(nodes)
                event.set()

    async def _on_interest_update(self, peer_addr: str, msg: dict) -> None:
        existing = self._routing.get_peer_caps(peer_addr)
        self._routing.register_peer(peer_addr, {
            "agents": [{"name": c} for c in existing.get("caps", set())],
            "tools": [], "models": [],
        }, msg.get("interests", []))

    async def _on_task(self, peer_addr: str, msg: dict) -> None:
        try:
            task_id = msg.get("id", "")
            caller_id = msg.get("caller", "")
            capability = msg.get("capability", "")

            # Verifica assinatura
            if self._verify_peers and msg.get("signature") and caller_id:
                verify_data = {k: v for k, v in msg.items() if k != "signature"}
                caller_pub = await self._get_caller_pubkey(caller_id)
                if caller_pub:
                    from elo.security import verify_signature
                    if not verify_signature(caller_pub, verify_data, msg["signature"]):
                        logger.warning("[elo] bad signature from %s", caller_id[:12])
                        err = result_msg(task_id, "error",
                                        error={"code": "BAD_SIGNATURE", "message": "Invalid signature"})
                        await self._tcp.send_to(peer_addr, err)
                        return

            payload = msg.get("payload", {})

            logger.debug("[elo] task received | id=%s capability=%s from=%s",
                         task_id, capability, caller_id[:12] if caller_id else "?")

            task = Task(id=task_id, target=msg.get("target", ""), caller=caller_id,
                       capability=capability, payload=payload,
                       ttl_s=msg.get("ttl_s", 60),
                       signature=msg.get("signature", ""))

            if capability == "health":
                result_payload = {
                    "node_id": self._node_id,
                    "peers_count": self._tcp.peer_count,
                    "uptime_seconds": int(time.time() - self._started_at),
                    "last_heartbeat": int(self._last_heartbeat_received),
                    "version": self._version,
                }
            elif self._task_handler:
                result_payload = await self._task_handler(task)
            else:
                result_payload = {"message": "no handler registered"}

            result = result_msg(task_id, "success", payload=result_payload)
            # Assina resultado para garantir autenticidade
            result_no_sig = {k: v for k, v in result.items() if k != "signature"}
            result["signature"] = self._identity.sign(result_no_sig)
            await self._tcp.send_to(peer_addr, result)

        except Exception as e:
            logger.exception("[elo] task error")
            try:
                err = result_msg(msg.get("id", "unknown"), "error",
                                error={"code": "INTERNAL", "message": str(e)})
                await self._tcp.send_to(peer_addr, err)
            except Exception:
                pass

    async def _on_result(self, peer_addr: str, msg: dict) -> None:
        task_id = msg.get("id", "")

        # Verifica assinatura do resultado se verify_peers estiver ativo
        if self._verify_peers and msg.get("signature"):
            result_no_sig = {k: v for k, v in msg.items() if k != "signature"}
            # Extrai caller_id do pending_result (já que o caller original sabe quem enviou)
            # O peer que enviou é conhecido via peer_addr — extraímos node_id do prefixo
            peer_node_id = peer_addr.split("@")[0] if "@" in peer_addr else ""
            if peer_node_id:
                caller_pub = await self._get_caller_pubkey(peer_node_id)
                if caller_pub:
                    from elo.security import verify_signature
                    if not verify_signature(caller_pub, result_no_sig, msg["signature"]):
                        logger.warning("[elo] bad signature on result from %s", peer_node_id[:12])
                        return  # descarta resultado com assinatura inválida

        future = self._pending_results.get(task_id)
        if future and not future.done():
            status = msg.get("status", "error")
            if status == "success":
                future.set_result(Result.success(task_id, msg.get("payload", {})))
            else:
                future.set_result(Result.make_error(
                    task_id,
                    msg.get("error", {}).get("code", "UNKNOWN") if msg.get("error") else "UNKNOWN",
                    msg.get("error", {}).get("message", "") if msg.get("error") else "",
                ))

    async def _on_bye(self, peer_addr: str, msg: dict) -> None:
        self._routing.remove_peer(peer_addr)
        if self._is_outbound_target(peer_addr):
            raw_addr = peer_addr.split("@")[-1] if "@" in peer_addr else peer_addr
            asyncio.create_task(self._schedule_reconnect(raw_addr))

    # ── relay via tracker ───────────────────────────────────

    async def send_task_via_tracker(
        self,
        tracker_node: str,
        target: str,
        capability: str,
        payload: dict[str, Any],
        *,
        ttl_s: int = 60,
    ) -> Result:
        """Send a task via tracker relay (for peers behind NAT/Docker).

        Args:
            tracker_node: node_id or addr of tracker (empty = auto)
            target: node_id prefix or name of the destination
            capability: capability to invoke on destination
            payload: task payload
        """
        task_id = str(uuid.uuid4())
        relay_payload = {
            "target": target,
            "capability": capability,
            "payload": payload,
            "ttl_s": ttl_s,
        }
        task_dict = p2p_task_msg(
            task_id, tracker_node or "", self._node_id, "relay", relay_payload
        )
        task_dict.pop("signature", None)
        task_dict["signature"] = self._identity.sign(task_dict)

        peer = tracker_node or self._routing.find_peer_for("relay")
        # Bug fix: tracker_node vem como node_id puro, mas send_to precisa
        # do formato completo "node_id@ip:port". Faz lookup nos peer_addresses.
        if peer and "@" not in peer and peer != "":
            for addr in self._tcp.peer_addresses:
                if addr.startswith(peer[:12] + "@"):
                    peer = addr
                    break
        if peer:
            try:
                await self._tcp.send_to(peer, task_dict)
                return await self._wait_for_result(task_id, peer)
            except Exception as e:
                return Result.make_error(task_id, "RELAY_ERROR", str(e))

        return Result.make_error(task_id, "NO_TRACKER", "No tracker peer found")

    # ── helpers ───────────────────────────────────────────────

    async def _wait_for_result(self, task_id: str, peer_addr: str) -> Result:
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending_results[task_id] = future
        try:
            return await asyncio.wait_for(future, timeout=30)
        except asyncio.TimeoutError:
            return Result.make_error(task_id, "TIMEOUT", "No response")
        finally:
            self._pending_results.pop(task_id, None)

    async def _query_capability(self, capability: str, ttl: int = 5,
                                timeout: float = 5.0) -> str | None:
        query_id = str(uuid.uuid4())[:8]
        collected: list[dict[str, Any]] = []
        event = asyncio.Event()
        self._pending_queries[query_id] = (collected, event, time.time())
        await self._tcp.broadcast(query_msg(capability, query_id, ttl))
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass
        finally:
            self._pending_queries.pop(query_id, None)
        if collected:
            return collected[0].get("addr", None)
        return None

    async def _get_caller_pubkey(self, node_id: str) -> Any | None:
        now = time.time()
        if node_id in self._pubkey_cache:
            pubkey, expires = self._pubkey_cache[node_id]
            if now < expires:
                return pubkey
            del self._pubkey_cache[node_id]
        try:
            from elo.security import id_to_pubkey
            pubkey = id_to_pubkey(node_id)
            self._pubkey_cache[node_id] = (pubkey, now + self._cache_ttl_s)
            return pubkey
        except Exception:
            return None

    async def _flush_pending(self) -> None:
        """Tenta reenviar todos os tasks pendentes."""
        if self._flushing_pending:
            return
        self._flushing_pending = True

        try:
            tasks = self._pending_queue.load_all()
            if not tasks:
                return

            now = time.time()
            remaining = []
            sent_any = False

            for task in tasks:
                # Expire after 10 minutes (600s)
                if now - task.created_at > 600:
                    logger.warning("[node] pending task %s expired (10min timeout)", task.task_id)
                    continue

                # Check if target node or capability has a peer available
                peer = None
                if task.target_node:
                    for addr in self._tcp.peer_addresses:
                        if addr.startswith(task.target_node[:12] + "@"):
                            peer = addr
                            break
                else:
                    peer = self._routing.find_peer_for(task.capability)

                if peer or self._routing.find_peer_for("relay"):
                    asyncio.create_task(self._retry_single_task(task))
                    sent_any = True
                else:
                    task.retries += 1
                    remaining.append(task)

            if sent_any or len(remaining) != len(tasks):
                self._pending_queue.save_all(remaining)

        except Exception as e:
            logger.debug("[node] error in flush pending: %s", e)
        finally:
            self._flushing_pending = False

    async def _retry_single_task(self, task: PendingTask) -> None:
        try:
            result = await self.send_task(
                task.target_node,
                task.capability,
                task.payload,
                ttl_s=task.ttl_s,
                _bypass_queue=True
            )
            if result.status == "error":
                # If retry failed, put it back in queue if not expired
                now = time.time()
                if now - task.created_at <= 600:
                    logger.info("[node] retry failed for task %s, re-queuing", task.task_id)
                    tasks = self._pending_queue.load_all()
                    if not any(t.task_id == task.task_id for t in tasks):
                        task.retries += 1
                        tasks.append(task)
                        self._pending_queue.save_all(tasks)
            else:
                logger.info("[node] successfully sent pending task %s", task.task_id)
        except Exception as e:
            logger.debug("[node] error in retry single task: %s", e)

    def _is_outbound_target(self, peer_addr: str) -> bool:
        raw_addr = peer_addr.split("@")[-1] if "@" in peer_addr else peer_addr
        if self._tracker_host and self._tracker_host == raw_addr:
            return True
        if raw_addr in self._initial_peers:
            return True
        return False

    def _build_hello_msg(self) -> dict:
        return hello_msg(
            self._node_id,
            self._tracker.get_public_caps(),
            list(self._routing.local_interests),
            self._tracker.visibility,
            self._version,
        )

    async def _schedule_reconnect(self, addr: str) -> None:
        if addr in self._reconnecting_peers:
            return
        self._reconnecting_peers.add(addr)

        try:
            while not self._shutdown_event.is_set():
                # Check if already connected
                is_connected = False
                for c_addr in self._tcp.peer_addresses:
                    raw_c_addr = c_addr.split("@")[-1] if "@" in c_addr else c_addr
                    if raw_c_addr == addr:
                        is_connected = True
                        break

                if is_connected:
                    self._reconnect_backoff[addr] = 0
                    break

                attempts = self._reconnect_backoff.get(addr, 0)
                delay = min(2 ** attempts, 30)
                self._reconnect_backoff[addr] = attempts + 1

                logger.info("[node] scheduling reconnect to %s in %ds (attempt %d)", addr, delay, attempts)

                try:
                    await asyncio.wait_for(self._shutdown_event.wait(), timeout=delay)
                except asyncio.TimeoutError:
                    pass

                if self._shutdown_event.is_set():
                    break

                hello = self._build_hello_msg()
                res = await self._tcp.connect_to_peer(addr, hello_payload=hello)
                if res:
                    logger.info("[node] successfully reconnected to %s", addr)
                    self._reconnect_backoff[addr] = 0
                    break
        except Exception as e:
            logger.debug("[node] error in reconnect for %s: %s", addr, e)
        finally:
            self._reconnecting_peers.discard(addr)

    async def _on_discovered_peer(self, node_id: str, peer_addr: str) -> None:
        for addr in self._tcp.peer_addresses:
            if addr.endswith(peer_addr) or addr.startswith(node_id[:12] + "@"):
                return

        logger.info("[node] discovered peer on LAN: %s (%s)", peer_addr, node_id[:12])
        hello = self._build_hello_msg()
        try:
            await self._tcp.connect_to_peer(peer_addr, hello_payload=hello)
        except Exception as e:
            logger.debug("[node] failed to connect to discovered peer %s: %s", peer_addr, e)

    # ── contexto ──────────────────────────────────────────────

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *args):
        await self.disconnect()
