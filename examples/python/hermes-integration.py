"""
Bridge Elo ↔ Hermes Agent — exemplo usando o SDK Python P2P.

Demonstra como um skill do Hermes se registra na malha Elo.
"""

import asyncio

from elo import Node


async def main():
    node = Node(
        "hermes-worker",
        port=7878,
        labels={"hermes_skill": "analyst"},
    )
    await node.connect()
    await node.register(
        agent_details=[{"name": "analyst-gpt4o", "model": "gpt-4o",
                        "description": "Análise de dados"}],
        tool_details=[{"name": "web-search", "description": "Busca na web",
                       "version": "1.0"}],
    )

    @node.on_task
    async def handle(task):
        print(f"[hermes-elo] task: {task.capability}")
        return {"handled_by": "hermes", "task_id": task.id}

    print(f"[elo-hermes] bridge active | node={node.node_id}")
    await node.run()


asyncio.run(main())
