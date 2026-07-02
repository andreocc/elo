"""
Elo — malha P2P de mensagens para agentes de IA.

Um processo. Uma porta TCP. Uma chave ed25519.
Zero infraestrutura externa.

Uso:
    from elo import Node

    node = Node("meu-agente", port=7878)
    await node.connect()
    await node.register(agents=["analyst"], tools=["web-search"])

    @node.on_task
    async def handle(task):
        return {"result": "ok"}

    await node.run()
"""

from elo.node import Node
from elo.security import EphemeralIdentity, generate_and_save_identity, load_identity
from elo.types import Task, Result, Event, NodeInfo, Capabilities

__all__ = [
    "Node", "Task", "Result", "Event", "NodeInfo", "Capabilities",
    "EphemeralIdentity", "generate_and_save_identity", "load_identity",
]
__version__ = "0.4.8"
