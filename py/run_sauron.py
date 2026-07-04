#!/usr/bin/env python3
"""Start Sauron's Elo node. Writes to stdout - pipe to a file for persistence."""
import asyncio, logging, sys

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(name)s:%(message)s",
    stream=sys.stdout,
    force=True,
)

from elo import Node
from elo.security import load_identity

async def main():
    node = Node("sauron-elo", port=0, peers=["100.91.215.113:7878"], identity=load_identity())
    await node.connect()
    await node.register(agents=["ping", "status", "agent-info", "hermes"])

    @node.on_task
    async def handle(task):
        return {
            "result": f"by Sauron: {task.capability}",
            "payload": task.payload,
            "from": node.node_id,
        }

    logging.getLogger("elo.startup").info(
        f"Node running port={node.port} id={node.node_id[:12]}"
    )
    sys.stdout.flush()
    await node.run()

asyncio.run(main())
