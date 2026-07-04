#!/usr/bin/env python3
"""Sauron Elo Node — comunicação bilateral com SAM.

Conecta a SAM como peer. Porta dinâmica (0 = aleatória).
Usa identidade persistente em ~/.elo/identity.seed.
"""
import asyncio, logging, sys

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(name)s:%(message)s",
    stream=sys.stdout,
    force=True,
)

from elo import Node
from elo.security import load_identity

log = logging.getLogger("sauron-elo")

async def main():
    identity = load_identity()
    node_id = identity.node_id[:12]
    log.info(f"Sauron identity loaded | id={node_id}")

    node = Node(
        "sauron-elo",
        port=0,                    # porta dinâmica (evita conflito WSL)
        peers=["100.91.215.113:7878"],  # SAM (Tailscale)
        tracker="public",
        identity=identity,
        labels={"host": "sauron", "role": "agent", "location": "wsl"},
    )

    await node.connect()
    await node.register(
        agent_details=[
            {"name": "ping",       "description": "Echo pong responder"},
            {"name": "hermes",     "description": "Hermes Agent interface"},
            {"name": "status",     "description": "System status info"},
            {"name": "agent-info", "description": "Agent capabilities discovery"},
        ]
    )

    @node.on_task
    async def handle(task):
        log.info(f"task received | cap={task.capability} from={task.caller[:12] if task.caller else '?'}")

        if task.capability == "ping":
            return {
                "status": "ok",
                "message": "pong from Sauron",
                "node_id": node.node_id[:12],
            }

        return {
            "result": f"by Sauron: {task.capability}",
            "payload": task.payload,
            "from": node.node_id[:12],
        }

    log.info(f"Sauron Elo node running | id={node_id} port={node.port}")

    await node.run()

if __name__ == "__main__":
    asyncio.run(main())
