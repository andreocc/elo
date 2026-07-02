# Runbook Elo v0.4

## Quickstart

### Pré-requisitos
- Python 3.11+

### 1. Instalar
```bash
cd py && pip install -e .
```

### 2. Verificar identidade
```bash
python -m elo status
```

### 3. Rodar um nó
```python
import asyncio
from elo import Node

async def main():
    node = Node("node-dev-1", port=7878)
    await node.connect()
    await node.register(agents=["hello-agent"])
    await node.run()

asyncio.run(main())
```

Ou via CLI:
```bash
python -m elo serve
```

## Conectar-se a peers

⚠️ **Importante:** sem `peers=`, o nó só escuta — nunca inicia conexão com ninguém.

```python
# Só escuta (passivo — aguarda conexões de entrada)
node = Node("meu-no", port=7878)

# Conecta-se ao tracker + escuta
node = Node("meu-no", port=7878, peers=["100.91.215.113:7878"])
```

Quando conectado a um tracker público/privado, o handshake HELLO→HELLO_ACK já inclui
a lista de peers conhecidos — a conexão a eles é automática.

## Deploy

### Produção com Tailscale (recomendado)

```python
node = Node(
    "meu-servidor-1",
    port=7878,
    tracker="private",
    allowlist=["Pabc123...", "Pdef456..."],
    heartbeat_interval_s=15,
    labels={"region": "us-east-1", "env": "production"},
)
```

### Docker

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY py/ /app/py/
RUN pip install /app/py
COPY meu_no.py /app/
EXPOSE 7878
CMD ["python", "/app/meu_no.py"]
```

## Gerenciamento de peers

### Ver peers com handshake completo
```python
# Peers que completaram HELLO+HELLO_ACK
peers = node.get_known_peers()
# → [{"addr": "ID@IP:PORT", "caps": [...], "interests": [...]}]
```

### Ver peers localmente conhecidos (TCP + InterestTable, sem rede)
```python
peers = await node.get_known_peers_local()
# → [{"addr": "...", "connected": True/False, "caps": [...], "via": "tcp|routing|both"}]
```

### Descobrir peers via QUERY broadcast
```python
peers = await node.discover_peers_network(timeout=5.0)
# → merge de descoberta via broadcast + peers locais
```

⚠️ `discover_peers_network()` usa QUERY com capability vazia — nós comuns não
respondem a QUERY vazio. Funciona principalmente para mesclar peers locais.
Refinamento futuro: novo tipo de mensagem DISCOVER.

### discover_peers() — depreciado
```python
peers = await node.discover_peers()  # ← mantido por compatibilidade
# Equivalente a get_known_peers_local(). Renomeado em v0.4.4.
```

## Enviar tasks

### send_task() — fallback automático via tracker
```python
result = await node.send_task("", "ping", {"msg": "hello"})
```

Chain de resolução (v0.4.4+):
1. Tenta `peer_addresses` (conexão direta)
2. Tenta InterestTable local (`find_peer_for`)
3. QUERY broadcast
4. **Fallback:** `send_task_via_tracker()` ← novo em v0.4.4
5. Se tudo falha: `Result(status="error", error={"code": "NO_PEER"})`

Antes o passo 4 não existia — retornava NO_PEER mesmo com tracker online.

### send_task_via_tracker() — relay explícito
```python
result = await node.send_task_via_tracker(
    tracker_node="",          # vazio = auto-descobre
    target="sauron-elo",      # node_id prefix ou nome
    capability="ping",
    payload={"msg": "hello"},
)
```

## Troubleshooting

### Tabela de sintomas

| Sintoma | Causa provável | Ação |
|---------|---------------|------|
| `ConnectionRefusedError` | Peer offline ou porta errada | Verificar porta no peer alvo |
| `NO_PEER` em task | Nenhum peer com a capability + tracker sem relay | `node.get_known_peers()` |
| Timeout em task | Peer lento ou desconectado | Aumentar `ttl_s` |
| Assinatura inválida | Peer com identidade diferente | Verificar `node_id` |
| `discover_peers()` vazio | Método é local-only desde v0.4.4 | Usar `get_known_peers()` |
| Cliente não descobre ninguém | `peers=` não foi passado no construtor | Obrigatório para outbound |

### Bug conhecido v0.4.3 corrigido em v0.4.4

Se você usa v0.4.3, `send_task()` nunca tenta o tracker — retorna NO_PEER
mesmo com tracker online. Upgrade para v0.4.4+ resolve.

```bash
pip install elo-node>=0.4.4
```

## Recuperação

### Nó perdeu conectividade
Identidade padrão carrega do disco se existir (`~/.elo/identity.seed`). Para gerar:
```bash
python -m elo init
```

### Rollback
1. Parar o processo (Ctrl+C — graceful shutdown com BYE)
2. Reverter o SDK: `git checkout <tag> && cd py && pip install -e .`
3. Protocolo `elo.v1` é backward-compatible
4. Reiniciar

## Arquitetura de descoberta (v0.4.4)

```
Cliente                    Tracker                         Peer
   |                         |                              |
   |--- HELLO -------------->|                              |
   |                         |-- registra peer              |
   |<-- HELLO_ACK + known ---|                              |
   |       peers             |                              |
   |                         |                              |
   |--- HELLO -------------------------------------------->|
   |<-- HELLO_ACK -----------------------------------------|
   |                         |                              |
   |--- TASK (relay) ------->|                              |
   |                         |--- TASK -------------------->|
   |                         |<-- RESULT -------------------|
   |<-- RESULT --------------|                              |
```

**Fluxo:**
1. Cliente conecta ao tracker com `peers=["IP:PORT"]`
2. Tracker responde HELLO_ACK + lista de peers conhecidos
3. Cliente conecta-se automaticamente a cada peer listado
4. Quando `send_task()` falha localmente, tenta tracker como relay
5. Tracker reencaminha a task ao destino e retorna o resultado

**Casos que ainda retornam NO_PEER:**
- Tracker sem capability `relay` registrada
- Destino nunca conectou ao tracker
- Timeout na resposta do relay (>30s)
