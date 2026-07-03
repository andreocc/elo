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
    node = Node("my-agent", port=7878, peers=["TRACKER_IP:7878"])
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
- **Relay via tracker** — nodes behind NAT/Docker communicate through a tracker
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

## Quick Start

### 1. Connect to a tracker

⚠️ `peers=` is **required** for outbound connections. Without it the node only listens.

```python
node = Node("agent-1", port=7878, peers=["TRACKER_IP:7878"])
await node.connect()
```

On HELLO handshake with a tracker (v0.4.4+), known peers are automatically exchanged — new nodes are discovered on connect.

### 2. Register capabilities

```python
await node.register(agents=["ping", "analyst"], tools=["web-search"])
```

### 3. Send tasks

```python
# Auto-fallback: direct → InterestTable → QUERY → tracker relay → NO_PEER
result = await node.send_task("", "ping", {"msg": "hello"})
# → Result(status="success", payload={...})
```

### 4. Discover peers

```python
# Peers with full handshake
known = node.get_known_peers()

# Broadcast QUERY across the mesh (returns node_id + addresses)
peers = await node.discover_peers_network(timeout=5.0)

# Legacy (local-only, deprecated)
local = await node.discover_peers()
```

### 5. Relay through tracker (NAT/Docker)

```python
# Explicit relay for NAT'd nodes
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
         │       Tracker (optional)          │
         └────────────── DHT ───────────────┘
```

Each node:
1. Generates an ed25519 identity on first run
2. Listens on a TCP port
3. Announces capabilities (e.g. "analyst", "web-search")
4. Discovers other nodes via shared tracker or manual peers
5. Exchanges signed messages (tasks, results, events)

## Private Tracker

For 3+ nodes or nodes behind NAT/Docker (no public port), use a **private tracker**:

1. Pick an always-online node as tracker (e.g. SAM at `TRACKER_IP:7878`)
2. Run `examples/python/tracker.py` on it
3. All other nodes connect via `peers=["<tracker-ip>:7878"]`
4. The tracker relays tasks between nodes automatically

```python
# Client node
node = Node("my-node", port=0, peers=["TRACKER_IP:7878"])
```

### Stale peer prevention (v0.4.10)

When a node restarts (Docker, VM reboot) with the same identity but a **different port**, the tracker previously kept the stale entry — tasks could fail with "Peer not connected".

**Fixed in v0.4.10:** the tracker now removes any existing peer entry matching the same `node_id` prefix on HELLO, before registering the new connection. Identity stays persistent (ed25519 key), port stays dynamic — both preserved.

## Changelog

| Version | Highlights |
|---------|------------|
| 0.4.10 | **Stale peer fix** — tracker removes old entry on reconnection with same identity, different port |
| 0.4.9 | `node_id` included in `discover_peers_network()` response |
| 0.4.8 | `send_task()` routing fix — correctly falls back to tracker relay when target is offline |
| 0.4.7 | Rate limiting, result signing, broadcast loop fix |
| 0.4.6 | Documentation update, `__version__` fix |
| 0.4.5 | Multi-response discover, tracker returns all peers on query |
| 0.4.4 | HELLO_ACK with known_peers, send_task auto-fallback tracker |
| 0.4.3 | Relay via tracker, `send_task_via_tracker()` |
| 0.4.2 | `discover_peers()` fix, `get_known_peers()` API |
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
