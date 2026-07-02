# Arquitetura Elo v0.4 — P2P Mesh

## Visão geral

Elo é uma malha peer-to-peer. Cada nó é um servidor TCP que se conecta diretamente a outros nós. Zero infraestrutura externa.

```
┌─────────────────────────────────────────────────┐
│            APLICAÇÃO (Agentes)                  │
│  Hermes │ LangChain │ raw Python │ qualquer     │
├─────────────────────────────────────────────────┤
│         INTEGRAÇÃO (Elo Node — API pública)     │
│  connect() │ register() │ on_task() │ run()     │
├─────────────────────────────────────────────────┤
│              ROTEAMENTO (Interest Table)        │
│  caps → peers │ interests → forwarding          │
├─────────────────────────────────────────────────┤
│              TRANSPORTE (TCP)                   │
│  TCP server │ peer connections │ framed JSON   │
├─────────────────────────────────────────────────┤
│              IDENTIDADE (ed25519)               │
│  ed25519 │ assinatura │ node_id = pubkey       │
└─────────────────────────────────────────────────┘
```

## Camada 1 — Identidade (ed25519)

Cada nó possui par de chaves ed25519. A chave pública é o `node_id`.

```
node_id = base64_urlsafe(ed25519_pubkey)   # 32 bytes → ~43 chars
```

- **Persistente**: se `~/.elo/identity.seed` existe, carrega automaticamente
- **Efêmera**: se não existe, gera nova com warning

## Camada 2 — Transporte (TCP)

Cada nó abre servidor TCP (padrão: porta 7878).

**Wire protocol:** frames `[4 bytes big-endian length][JSON payload]` (max 1 MB).

### Tipos de mensagem

| Tipo | Direção | Propósito |
|------|---------|-----------|
| HELLO | peer→peer | Handshake: node_id, caps, interests, tracker |
| HELLO_ACK | peer→peer | Resposta ao HELLO |
| QUERY | broadcast | Buscar capability na mesh (TTL) |
| QUERY_RESP | unicast | Endereços de nós com a capability |
| INTEREST_UPDATE | broadcast | Atualização de interests |
| TASK | unicast | Executar capability (assinada) |
| RESULT | unicast | Resultado da task |
| HEARTBEAT | unicast | Keep-alive (30s) |
| BYE | unicast | Graceful disconnect |

## Camada 3 — Roteamento (Interest Table)

```
InterestTable:
  local_caps:      {"analyst", "web-search"}     ← o que EU tenho
  local_interests: {"writer"}                     ← o que EU procuro
  forwarding:      "analyst" → {peer1, peer3}     ← capability → peers
```

**Roteamento de task:**
1. Forwarding table hit → envia direto
2. Miss → broadcast QUERY → QUERY_RESP → conecta → envia

## Camada 4 — Integração (API pública)

```python
from elo import Node

node = Node("meu-agente", port=7878, tracker="public")
await node.connect()
await node.register(agents=["analyst"], tools=["web-search"])

@node.on_task
async def handle(task):
    return {"result": "ok"}

await node.run()
```

### Parâmetros

| Parâmetro | Padrão | Descrição |
|-----------|--------|-----------|
| `name` | (obrigatório) | Nome do nó |
| `port` | 7878 | Porta TCP |
| `peers` | `[]` | Lista manual `["ip:port", ...]` |
| `tracker` | `"public"` | `"public"` ou `"private"` |
| `allowlist` | `[]` | Node IDs autorizados (private) |
| `verify_peers` | `True` | Verificar assinatura ed25519 |
| `identity` | auto | Carrega do disco ou gera efêmera |

## Segurança

- **Autenticação**: `node_id` = chave pública ed25519
- **Assinatura**: canonical JSON → ed25519 sign (toda task)
- **Rede**: WireGuard/Tailscale recomendado para WAN
