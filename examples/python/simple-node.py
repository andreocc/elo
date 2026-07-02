"""
Elo Node — exemplo funcional usando o SDK Python P2P.

Uso:
    cd py && pip install -e .
    python examples/python/simple-node.py
"""

import asyncio
import signal

from elo import Node


async def main():
    node = Node("exemplo-python", port=7878)
    await node.connect()
    await node.register(
        agents=["echo-agent"],
        tools=["ping"],
    )

    @node.on_task
    async def handle(task):
        print(f"[task] {task.capability}: {task.payload}")
        return {
            "echo": task.payload,
            "processed_by": node.node_id,
        }

    # Graceful shutdown no SIGINT/SIGTERM
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(node.disconnect()))

    print(f"[elo] running | node={node.node_id}")
    await node.run()


asyncio.run(main())
