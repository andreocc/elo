"""Elo Tracker Node — discovery + relay para peers atrás de NAT/Docker.

Uso:
    python tracker.py

Todos os nós Elo se conectam ao tracker. O tracker:
- Discovery: responde quem está online e suas capabilities
- Relay: reencaminha tasks para peers que não expõem porta (Docker/NAT)
"""

import asyncio
import logging
import uuid
import time

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

from elo import Node, Task, Result
from elo.transport import task_msg as p2p_task_msg

TRACKER_ID = "elo-tracker"


async def main():
    node = Node(TRACKER_ID, port=7878)
    await node.connect()
    await node.register(agents=["tracker", "echo", "discovery", "relay"])

    @node.on_task
    async def handle(task):
        logger = logging.getLogger("tracker")

        # ── Relay: reencaminha task para outro peer ──
        if task.capability == "relay":
            target = task.payload.get("target", "")
            cap = task.payload.get("capability", "")
            payload = task.payload.get("payload", {})
            logger.info(f"Relay: {task.caller[:12]} -> {target[:16]} ({cap})")

            # Encontra o peer — match por name, node_id prefix, ou addr
            peer_addr = None
            candidates = node._routing.known_peers  # "prefix@ip:port"
            for addr in candidates:
                if target in addr:  # match substring: name, node_id, ip
                    peer_addr = addr
                    break
            # Se não achou, pega o primeiro peer com capability 'ping' ou 'echo'
            if not peer_addr and candidates:
                for c in [cap, "ping", "echo"]:
                    p = node._routing.find_peer_for(c)
                    if p:
                        peer_addr = p
                        break
            if not peer_addr and candidates:
                peer_addr = candidates[0]  # fallback: primeiro peer

            if not peer_addr:
                return {"error": f"target not found: {target}", "known": node._routing.known_peers}

            # Cria nova task para o destino
            relay_task_id = str(uuid.uuid4())
            task_dict = p2p_task_msg(
                relay_task_id, peer_addr, node.node_id, cap, payload
            )
            task_dict.pop("signature", None)
            task_dict["signature"] = node._identity.sign(task_dict)

            try:
                await node._tcp.send_to(peer_addr, task_dict)
                # Aguarda resultado (timeout 30s)
                future = asyncio.get_event_loop().create_future()
                node._pending_results[relay_task_id] = future
                result = await asyncio.wait_for(future, timeout=30)
                return {
                    "relay_status": "success",
                    "result": result.payload if hasattr(result, 'payload') else result,
                    "relayed_by": node.node_id[:12],
                }
            except asyncio.TimeoutError:
                return {"relay_status": "timeout", "target": target}
            except Exception as e:
                return {"relay_status": "error", "error": str(e)}
            finally:
                node._pending_results.pop(relay_task_id, None)

        # ── Discovery: lista todos os peers ──
        if task.capability == "discovery":
            peers = node.get_known_peers()
            return {
                "tracker_id": node.node_id[:16],
                "peers_connected": len(peers),
                "known_peers": peers,
                "local_caps": list(node._routing.local_caps),
            }

        # ── Echo padrão ──
        return {"echo": task.payload, "from": node.node_id, "node": "tracker"}

    logger = logging.getLogger("tracker")
    logger.info(f"Tracker running | port={node.port} id={node.node_id[:12]}")
    logger.info("Capabilities: discovery + relay (NAT/Docker forwarding)")
    await node.run()


if __name__ == "__main__":
    asyncio.run(main())
