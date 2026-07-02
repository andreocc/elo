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
)
from elo.security import EphemeralIdentity, load_identity, pubkey_to_id
from elo.types import Capabilities, Result, Task

logger = logging.getLogger("elo")

DEFAULT_DATA_DIR = Path.home() / ".elo"


def _load_or_generate_identity() -> EphemeralIdentity:
    """Carrega identidade persistente se existir, senão gera efêmera."""
    seed_path = DEFAULT_DATA_DIR / "identity.seed"
    if seed_path.exists():
        try:
            priv, _ = load_identity(DEFAULT_DATA_DIR)
            pub = priv.public_key()
            node_id = pubkey_to_id(pub)
            logger.info("[elo] loaded persistent identity from %s", DEFAULT_DATA_DIR)
            identity = EphemeralIdentity.__new__(EphemeralIdentity)
            identity._private_key = priv
            identity._public_key = pub
            return identity
        except Exception as e:
            logger.warning("[elo] failed to load identity: %s — generating ephemeral", e)
    logger.info("[elo] no persistent identity — generated ephemeral (use 'python -m elo init' to persist)")
    return EphemeralIdentity()


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
        version: str = "0.4.2",
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
        self._identity = identity or _load_or_generate_identity()
        self._node_id = self._identity.node_id

        # Transporte
        self._tcp = TCPManager(self._node_id, port=port)

        # Roteamento
        self._routing = InterestTable()
        self._tracker = LocalTracker(visibility=tracker)
        if allowlist:
            for nid in allowlist:
                self._tracker.allow_peer(nid)

        # Estado
        self._task_handler: Callable[[Task], Awaitable[dict[str, Any]]] | None = None
        self._shutdown_event = asyncio.Event()
        self._pending_results: dict[str, asyncio.Future] = {}
        self._pending_queries: dict[str, tuple[asyncio.Future, float]] = {}

        # Cache de pubkeys para verificação de assinatura
        self._pubkey_cache: dict[str, tuple[Any, float]] = {}
        self._cache_ttl_s = heartbeat_interval_s * 5

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

        # Conecta a peers manuais
        hello = hello_msg(
            self._node_id,
            self._tracker.get_public_caps(),
            list(self._routing.local_interests),
            self._tracker.visibility,
            self._version,
        )
        for addr in self._initial_peers:
            await self._tcp.connect_to_peer(addr, hello_payload=hello)

        logger.info("[elo] connected | node=%s id=%s port=%d",
                     self._name, self._node_id[:12], actual_port)

    async def disconnect(self) -> None:
        self._shutdown_event.set()
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
                        payload: dict[str, Any], *, ttl_s: int = 60) -> Result:
        """Envia task e aguarda resultado. Descobre peer se target vazio."""
        if not self.connected:
            raise RuntimeError("Node not connected")

        task_id = str(uuid.uuid4())
        task_dict = p2p_task_msg(task_id, target_node, self._node_id, capability, payload)
        task_dict.pop("signature", None)
        task_dict["signature"] = self._identity.sign(task_dict)

        # Tenta encontrar peer
        peer = target_node if target_node and target_node in self._tcp.peer_addresses else None
        if not peer:
            peer = self._routing.find_peer_for(capability)

        # Se não encontrou, faz QUERY broadcast
        if not peer:
            peer = await self._query_capability(capability, ttl=5, timeout=5)
            if peer:
                hello = hello_msg(self._node_id, self._tracker.get_public_caps(),
                                  list(self._routing.local_interests),
                                  self._tracker.visibility, self._version)
                peer = await self._tcp.connect_to_peer(peer, hello_payload=hello)

        if peer:
            try:
                await self._tcp.send_to(peer, task_dict)
                return await self._wait_for_result(task_id, peer)
            except Exception as e:
                return Result.make_error(task_id, "SEND_ERROR", str(e))

        return Result.make_error(task_id, "NO_PEER", f"No peer for: {capability}")

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

    async def discover_peers(self) -> list[dict[str, Any]]:
        """Return all known peers with capabilities.

        Merges data from TCP connections (live) and InterestTable (registered).
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

    def get_known_peers(self) -> list[dict[str, Any]]:
        """Return peers registered in InterestTable (completed HELLO handshake).

        More reliable than discover_peers() — only includes peers that
        completed the full handshake (HELLO + HELLO_ACK).
        Meant for tracker/discovery use cases.
        """
        result = []
        for addr in self._routing.known_peers:
            info = self._routing.get_peer_caps(addr)
            result.append({
                "addr": addr,
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

        await self._shutdown_event.wait()
        heartbeat_task.cancel()

    # ── message dispatcher ────────────────────────────────────

    async def _handle_message(self, peer_addr: str, msg: dict[str, Any]) -> None:
        msg_type = msg.get("type", "")

        if msg_type == MessageType.HELLO:
            await self._on_hello(peer_addr, msg)
        elif msg_type == MessageType.HELLO_ACK:
            await self._on_hello(peer_addr, msg)
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
        elif msg_type == MessageType.BYE:
            await self._on_bye(peer_addr, msg)

    # ── protocol handlers ─────────────────────────────────────

    async def _on_hello(self, peer_addr: str, msg: dict) -> None:
        node_id = msg.get("node_id", "")
        caps = msg.get("caps", {})
        interests = msg.get("interests", [])
        self._routing.register_peer(peer_addr, caps, interests)

        ack = hello_ack_msg(self._node_id, self._tracker.get_caps_for_peer(node_id),
                            list(self._routing.local_interests), self._tracker.visibility)
        try:
            await self._tcp.send_to(peer_addr, ack)
        except Exception:
            pass

    async def _on_query(self, peer_addr: str, msg: dict) -> None:
        capability = msg.get("capability", "")
        query_id = msg.get("id", "")
        ttl = msg.get("ttl", 5)
        nodes = []
        if self._tracker.has_capability(capability):
            # Usa peer_addr (addr real do TCP) em vez de localhost — necessário para WAN/Tailscale
            nodes.append({"node_id": self._node_id[:12], "addr": peer_addr})
        for p in self._routing.find_all_peers_for(capability):
            nodes.append({"addr": p})
        if nodes:
            try:
                await self._tcp.send_to(peer_addr, query_resp_msg(query_id, nodes))
            except Exception:
                pass
        elif ttl > 1:
            await self._tcp.broadcast(query_msg(capability, query_id, ttl=ttl - 1), exclude={peer_addr})

    async def _on_query_resp(self, peer_addr: str, msg: dict) -> None:
        query_id = msg.get("id", "")
        if query_id in self._pending_queries:
            future, _ = self._pending_queries[query_id]
            nodes = msg.get("nodes", [])
            if nodes and not future.done():
                future.set_result(nodes[0].get("addr", ""))

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

            if self._task_handler:
                result_payload = await self._task_handler(task)
            else:
                result_payload = {"message": "no handler registered"}

            result = result_msg(task_id, "success", payload=result_payload)
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
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending_queries[query_id] = (future, time.time())
        await self._tcp.broadcast(query_msg(capability, query_id, ttl))
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            return None
        finally:
            self._pending_queries.pop(query_id, None)

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

    # ── contexto ──────────────────────────────────────────────

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *args):
        await self.disconnect()
