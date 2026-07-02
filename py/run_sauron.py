"""Sauron Elo node — connects to elo tracker on SAM (Tailscale)."""
import asyncio, logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
from elo import Node

async def main():
    node = Node("sauron-elo", port=0, peers=["100.91.215.113:7878"])
    await node.connect()
    await node.register(agents=["ping", "status", "agent-info", "hermes"])
    @node.on_task
    async def handle(task):
        return {"result": f"by Sauron: {task.capability}", "payload": task.payload, "from": node.node_id}
    logging.getLogger("sauron").info(f"Running port={node.port} id={node.node_id[:12]}")
    await node.run()

asyncio.run(main())
