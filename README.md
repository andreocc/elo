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
- **Capabilities** — publish/subscribe for agent skills across the mesh
- **Zero infrastructure** — no Kafka, Redis, NATS, or central server
- **Native CLI** — `python -m elo serve`, `status`, `init`, `id`
- **Relay via tracker** — nodes behind NAT/Docker can communicate through a tracker relay

## CLI

```bash
python -m elo status       # Node ID, hash, keys
python -m elo id           # Just the node_id
python -m elo pubkey       # Public key (hex + b64)
python -m elo init         # Generate persistent identity
python -m elo serve        # Start an interactive node
```

## Quick Start

### 1. Connect to a tracker

⚠️ `peers=` is **required** for outbound connections. Without it, the node listens only.

```python
# This connects to the tracker AND starts a TCP server
node = Node("agent-1", port=7878, peers=["100.91.215.113:7878"])
await node.connect()
```

When connecting to a v0.4.4+ tracker, the HELLO handshake automatically
includes the list of known peers — new nodes are discovered on connect.

### 2. Register capabilities

```python
await node.register(agents=["ping", "analyst"], tools=["web-search"])
```

### 3. Send tasks

```python
# Auto-fallback via tracker if no direct peer found
result = await node.send_task("", "ping", {"msg": "hello"})
# → Result(status="success", payload={...})
```

`send_task()` tries: direct peer → InterestTable → QUERY broadcast → **tracker relay** → NO_PEER

### 4. Discover peers

```python
# Peers that completed HELLO handshake
known = node.get_known_peers()

# Discover via QUERY broadcast (network scan)
peers = await node.discover_peers_network(timeout=5.0)

# Legacy (local-only, deprecated)
local = await node.discover_peers()
```

### 5. Relay via tracker (NAT/Docker)

```python
# Explicit relay call for nodes behind NAT
result = await node.send_task_via_tracker(
    tracker_node="",
    target="sauron-elo",
    capability="ping",
    payload={"msg": "hello"},
)
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

## Tracker (Private)

For 3+ nodes or nodes behind NAT/Docker, use a **private tracker**:

1. Pick an always-online node as tracker (e.g., SAM at `100.91.215.113:7878`)
2. Run `examples/python/tracker.py` on it
3. All other nodes connect via `peers=["<tracker-ip>:7878"]`
4. Tracker relays tasks between nodes automatically

```python
# Client node
node = Node("my-node", port=0, peers=["100.91.215.113:7878"])
```

## API Reference

| Method | Description |
|--------|-------------|
| `connect()` | Start TCP server + connect to initial peers |
| `register(agents=, tools=)` | Announce capabilities to the mesh |
| `send_task(target, cap, payload)` | Send task (auto-fallback via tracker) |
| `send_task_via_tracker(tracker, target, cap, payload)` | Explicit relay |
| `get_known_peers()` | Peers with completed handshake |
| `get_known_peers_local()` | Local-only peer merge (no network) |
| `discover_peers_network(timeout)` | QUERY broadcast + merge local peers |
| `run()` | Start event loop (heartbeat, message handling) |

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

## Changelog

| Version | Date | Highlights |
|---------|------|------------|
| 0.4.5 | 02/jul/2026 | Multi-response discover, tracker returns all peers on query |
| 0.4.4 | 02/jul/2026 | HELLO_ACK with known_peers, send_task auto-fallback tracker |
| 0.4.3 | 02/jul/2026 | Relay via tracker, send_task_via_tracker() |
| 0.4.2 | 02/jul/2026 | discover_peers() fix, get_known_peers() API |
| 0.4.0 | 02/jul/2026 | Initial release |

## Related Projects

- [Hermes Agent](https://hermes-agent.nousresearch.com) — autonomous agent runtime
- [Honcho](https://github.com/argmax-inc/honcho) — persistent memory for agents

---

> 🇧🇷 Leia em português: [README.pt-BR.md](README.pt-BR.md)
