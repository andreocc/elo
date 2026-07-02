# Elo 🔗

**Malha P2P de mensagens para agentes de IA. Um processo. Uma porta TCP. Uma chave ed25519.**

Elo é uma malha de mensagens peer-to-peer onde cada nó é um servidor TCP que se conecta diretamente a outros nós. Sem NATS. Sem Kafka. Sem Kubernetes. Apenas agentes conversando entre si.

```bash
pip install elo-node
```

```python
import asyncio
from elo import Node

async def main():
    node = Node("meu-agente", port=7878, peers=["100.91.215.113:7878"])
    await node.connect()
    await node.register(agents=["analyst"], tools=["web-search"])

    @node.on_task
    async def handle(task):
        return {"result": f"processado por {node.node_id}"}

    await node.run()

asyncio.run(main())
```

## Recursos

- **P2P descentralizado** — descoberta via tracker público ou DHT Kademlia
- **Assinatura ed25519** — identidade criptográfica, mensagens autenticadas
- **Capabilities** — publish/subscribe de capacidades entre nós
- **Zero infraestrutura** — sem Kafka, Redis, NATS, ou servidor central
- **CLI nativo** — `python -m elo serve`, `status`, `init`, `id`
- **Relay via tracker** — nós atrás de NAT/Docker se comunicam através do tracker

## CLI

```bash
python -m elo status       # Node ID, hash, chaves
python -m elo id           # Apenas o node_id
python -m elo pubkey       # Chave pública (hex + b64)
python -m elo init         # Gerar identidade persistente
python -m elo serve        # Iniciar nó interativo
```

## Início Rápido

### 1. Conectar a um tracker

⚠️ `peers=` é **obrigatório** para conexões de saída. Sem ele, o nó só escuta.

```python
node = Node("agente-1", port=7878, peers=["100.91.215.113:7878"])
await node.connect()
```

Ao conectar a um tracker v0.4.4+, o handshake HELLO inclui automaticamente
a lista de peers conhecidos — novos nós são descobertos na conexão.

### 2. Registrar capacidades

```python
await node.register(agents=["ping", "analyst"], tools=["web-search"])
```

### 3. Enviar tasks

```python
# Fallback automático via tracker se não achar peer direto
result = await node.send_task("", "ping", {"msg": "hello"})
# → Result(status="success", payload={...})
```

`send_task()` tenta: peer direto → InterestTable → QUERY broadcast → **relay do tracker** → NO_PEER

### 4. Descobrir peers

```python
# Peers com handshake completo
conhecidos = node.get_known_peers()

# Descobrir via QUERY broadcast (varredura de rede)
peers = await node.discover_peers_network(timeout=5.0)

# Legado (local-only, depreciado)
local = await node.discover_peers()
```

### 5. Relay via tracker (NAT/Docker)

```python
# Relay explícito para nós atrás de NAT
result = await node.send_task_via_tracker(
    tracker_node="",
    target="sauron-elo",
    capability="ping",
    payload={"msg": "hello"},
)
```

## Arquitetura

```
┌──────────────────┐     TCP/JSON     ┌──────────────────┐
│   Node A          │◄──────────────►│   Node B          │
│   chave ed25519   │                │   chave ed25519   │
│   Capacidades     │                │   Capacidades     │
│   Interesses      │                │   Interesses      │
└──────────────────┘                 └──────────────────┘
         │                                  │
         │       Tracker (opcional)          │
         └────────────── DHT ───────────────┘
```

Cada nó:
1. Gera identidade ed25519 na primeira execução
2. Escuta em uma porta TCP
3. Anuncia capacidades (ex: "analyst", "web-search")
4. Descobre outros nós via tracker compartilhado ou peers manuais
5. Troca mensagens assinadas (tasks, results, events)

## Tracker Privado

Para 3+ nós ou nós atrás de NAT/Docker (sem porta pública), use um **tracker privado**:

1. Escolha um nó sempre online como tracker (ex: SAM em `100.91.215.113:7878`)
2. Rode `examples/python/tracker.py` nele
3. Todos os outros nós conectam via `peers=["<ip-tracker>:7878"]`
4. O tracker faz relay de tasks entre os nós automaticamente

```python
# Nó cliente
node = Node("meu-no", port=0, peers=["100.91.215.113:7878"])
```

## API Reference

| Método | Descrição |
|--------|-----------|
| `connect()` | Iniciar servidor TCP + conectar a peers iniciais |
| `register(agents=, tools=)` | Anunciar capacidades na malha |
| `send_task(target, cap, payload)` | Enviar task (fallback automático via tracker) |
| `send_task_via_tracker(tracker, target, cap, payload)` | Relay explícito |
| `get_known_peers()` | Peers com handshake completo |
| `get_known_peers_local()` | Merge local-only (sem rede) |
| `discover_peers_network(timeout)` | QUERY broadcast + merge peers locais |
| `run()` | Loop principal (heartbeat, mensagens) |

## Compatibilidade

- Python 3.11+
- Linux, macOS, Windows

## Desenvolvimento

```bash
git clone https://github.com/andreocc/elo
cd elo/py
pip install -e ".[dev]"
pytest
```

## Changelog

| Versão | Data | Destaques |
|--------|------|-----------|
| 0.4.5 | 02/jul/2026 | discover multiresposta, tracker retorna todos peers |
| 0.4.4 | 02/jul/2026 | HELLO_ACK com known_peers, send_task fallback tracker |
| 0.4.3 | 02/jul/2026 | Relay via tracker, send_task_via_tracker() |
| 0.4.2 | 02/jul/2026 | discover_peers() fix, get_known_peers() API |
| 0.4.0 | 02/jul/2026 | Lançamento inicial |

## Projetos Relacionados

- [Hermes Agent](https://hermes-agent.nousresearch.com) — runtime de agentes autônomos
- [Honcho](https://github.com/argmax-inc/honcho) — memória persistente para agentes

---

> 🇺🇸 Read in English: [README.md](README.md)
