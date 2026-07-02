# Elo Node — P2P Message Mesh for AI Agents

**Zero infrastructure. One process. One TCP port. One ed25519 key.**

Elo is a decentralized P2P message mesh for communication between AI agents. No central server, no Kafka, no Redis, no NATS. Just direct TCP between nodes.

```bash
pip install elo-node
```

```python
import asyncio
from elo import Node

async def main():
    node = Node("my-agent", port=7878, peers=["100.91.215.113:7878"])
    await node.connect()
    await node.register(agents=["analyst"], tools=["web-search"])

    @node.on_task
    async def handle(task):
        return {"result": f"processed by {node.node_id}"}

    await node.run()

asyncio.run(main())
```

## Features

- **Decentralized P2P** — discovery via public tracker or Kademlia DHT
- **ed25519 signatures** — cryptographic identity, authenticated messages
- **Capabilities** — publish/subscribe of agent skills across the mesh
- **Relay via tracker** — nodes behind NAT/Docker can communicate through a tracker
- **Zero infra** — no Kafka, Redis, NATS, or central server
- **Native CLI** — `python -m elo serve`, `status`, `init`, `id`

## CLI

```bash
python -m elo status       # Node ID, hash, keys
python -m elo id           # Just the node_id
python -m elo pubkey       # Public key (hex + b64)
python -m elo init         # Generate persistent identity
python -m elo serve        # Start an interactive node
```

## Key Concepts

- **`peers=` is required** for outbound connections. Without it the node only listens.
- **`send_task()` auto-fallback:** direct → InterestTable → QUERY → **tracker relay** → NO_PEER
- **HELLO_ACK with known_peers:** tracker shares all peers on handshake (v0.4.4+)
- **`discover_peers_network()`** — QUERY broadcast across the mesh

## Changelog

| Version | Highlights |
|---------|------------|
| 0.4.5 | Multi-response discover, tracker returns all peers on query |
| 0.4.4 | HELLO_ACK with known_peers, send_task auto-fallback tracker |
| 0.4.3 | Relay via tracker, send_task_via_tracker() |
| 0.4.0 | Initial release |

## Compatibility

- Python 3.11+
- Linux, macOS, Windows

## Development

```bash
git clone https://github.com/andreocc/elo
cd elo/py
pip install -e ".[dev]"
pytest
```

## Related Projects

- [Hermes Agent](https://hermes-agent.nousresearch.com) — autonomous agent runtime
- [Honcho](https://github.com/argmax-inc/honcho) — persistent memory for agents
