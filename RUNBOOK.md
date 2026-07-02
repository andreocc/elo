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

### Adicionar peer manual
```python
node = Node("meu-no", port=7878, peers=["100.80.1.50:7878", "100.80.1.51:7878"])
```

### Ver peers conectados
```python
peers = await node.discover_peers()
```

## Troubleshooting

| Sintoma | Causa provável | Ação |
|---------|---------------|------|
| `ConnectionRefusedError` | Peer offline ou porta errada | Verificar porta no peer alvo |
| `NO_PEER` em task | Nenhum peer com a capability | `node.discover_peers()` |
| Timeout em task | Peer lento ou desconectado | Aumentar `ttl_s` |
| Assinatura inválida | Peer com identidade diferente | Verificar `node_id` |

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
