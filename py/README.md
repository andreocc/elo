# Elo Node — Malha P2P para Agentes de IA

**Zero infraestrutura. Um processo. Uma porta TCP. Uma chave ed25519.**

Elo é uma malha de mensagens P2P descentralizada para comunicação entre agentes de IA. Sem servidor central, sem Kafka, sem Redis, sem NATS. Apenas TCP direto entre nós.

```bash
pip install elo-node
```

```python
import asyncio
from elo import Node

async def main():
    node = Node("meu-agente", port=7878)
    await node.connect()
    await node.register(agents=["analyst"], tools=["web-search"])

    @node.on_task
    async def handle(task):
        return {"result": f"processed by {node.node_id}"}

    await node.run()

asyncio.run(main())
```

## Recursos

- **P2P descentralizado** — descoberta via tracker público ou DHT Kademlia
- **Assinatura ed25519** — identidade criptográfica, mensagens autenticadas
- **Capabilities** — publish/subscribe de capacidades entre nós
- **Zero infra** — sem Kafka, Redis, NATS, ou servidor central
- **CLI nativo** — `python -m elo serve`, `status`, `init`, `id`

## CLI

```bash
python -m elo status       # Node ID, hash, chaves
python -m elo id           # Apenas o node_id
python -m elo pubkey       # Chave pública (hex + b64)
python -m elo init         # Gerar identidade persistente
python -m elo serve        # Iniciar nó interativo
```

## Arquitetura

```
┌──────────────────┐     TCP/JSON     ┌──────────────────┐
│   Node A          │◄──────────────►│   Node B          │
│   ed25519 key     │                │   ed25519 key     │
│   Capabilities    │                │   Capabilities    │
│   Interests       │                │   Interests       │
└──────────────────┘                 └──────────────────┘
         │                                  │
         │         Tracker (opcional)        │
         └───────────── DHT ────────────────┘
```

Cada nó:
1. Gera identidade ed25519 na primeira execução
2. Escuta em uma porta TCP
3. Anuncia capacidades (ex: "analyst", "web-search")
4. Descobre outros nós via tracker compartilhado ou peers manuais
5. Troca mensagens assinadas (tasks, results, events)

## Compatibilidade

- Python 3.11+
- Linux, macOS, Windows

## Desenvolvimento

```bash
git clone https://github.com/xalq/elo
cd elo/py
pip install -e ".[dev]"
pytest
```

## Projetos Relacionados

- [Hermes Agent](https://hermes-agent.nousresearch.com) — runtime de agentes autônomos
- [Honcho](https://github.com/argmax-inc/honcho) — memória persistente para agentes
