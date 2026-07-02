# Elo 🔗

**P2P message mesh for AI agents. One process. One TCP port. One ed25519 key.**

Elo is a peer-to-peer message mesh where every node is a TCP server that connects directly to other nodes. No NATS. No Kafka. No Kubernetes. Just agents talking to each other.

```bash
pip install elo-node
```

```python
import asyncio
from elo import Node

async def main():
    node = Node("my-agent", port=7878)
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
- **Capabilities** — publish/subscribe for agent skills across the mesh
- **Zero infrastructure** — no Kafka, Redis, NATS, or central server
- **Native CLI** — `python -m elo serve`, `status`, `init`, `id`

## CLI

```bash
python -m elo status       # Node ID, hash, keys
python -m elo id           # Just the node_id
python -m elo pubkey       # Public key (hex + b64)
python -m elo init         # Generate persistent identity
python -m elo serve        # Start an interactive node
```

## Architecture

```
┌──────────────────┐     TCP/JSON     ┌──────────────────┐
│   Node A          │◄──────────────►│   Node B          │
│   ed25519 key     │                │   ed25519 key     │
│   Capabilities    │                │   Capabilities    │
│   Interests       │                │   Interests       │
└──────────────────┘                 └──────────────────┘
         │                                  │
         │        Tracker (optional)         │
         └────────────── DHT ───────────────┘
```

Each node:
1. Generates an ed25519 identity on first run
2. Listens on a TCP port
3. Announces capabilities (e.g. "analyst", "web-search")
4. Discovers other nodes via shared tracker or manual peers
5. Exchanges signed messages (tasks, results, events)

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

## WAN Test

Elo has been tested between two machines via Tailscale (Brazil — OCI VM ↔ WSL). Tasks, capabilities, and signature verification work across real network boundaries. See `docs/runbooks/` for deployment patterns.

## Related Projects

- [Hermes Agent](https://hermes-agent.nousresearch.com) — autonomous agent runtime
- [Honcho](https://github.com/argmax-inc/honcho) — persistent memory for agents

---

> 🇧🇷 Leia em português: [README.pt-BR.md](README.pt-BR.md)
