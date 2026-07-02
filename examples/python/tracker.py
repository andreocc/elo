"""Elo Tracker Node — ponto fixo na malha Tailscale para descoberta de peers.

Uso:
    python tracker.py

Todos os nós Elo se conectam a este tracker via `peers=["IP:7878"]`.
O tracker responde `discovery` com a lista de todos os peers conhecidos.
"""

import asyncio
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

from elo import Node


async def main():
    node = Node("elo-tracker", port=7878)
    await node.connect()
    await node.register(agents=["tracker", "echo", "discovery"])

    @node.on_task
    async def handle(task):
        if task.capability == "discovery":
            peers = []
            for addr in node._routing.known_peers:
                info = node._routing.get_peer_caps(addr)
                peers.append({
                    "addr": addr,
                    "caps": list(info.get("caps", set())),
                })
            return {
                "tracker_id": node.node_id[:16],
                "peers_connected": node.peer_count,
                "known_peers": peers,
                "local_caps": list(node._routing.local_caps),
            }
        return {"echo": task.payload, "from": node.node_id, "node": "tracker"}

    logger = logging.getLogger("tracker")
    logger.info(f"Elo tracker running on port {node.port} | id={node.node_id[:12]}")
    await node.run()


if __name__ == "__main__":
    asyncio.run(main())
