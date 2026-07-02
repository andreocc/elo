# Deploy Patterns v0.4

## Tailscale + Elo (recomendado)

### Por que

| Problema | Tailscale | Elo |
|----------|-----------|-----|
| Quem pode conectar? | Só nós na tailnet | — |
| Criptografia em trânsito | WireGuard | — |
| NAT traversal | Sim | — |
| Identidade do agente | — | ed25519 |
| Descoberta de capabilities | — | InterestTable |

### Setup

```bash
# Cada máquina na tailnet tem IP 100.x.x.x
# Nenhum servidor central necessário — apenas Elo + Tailscale

# Máquina A
python -c "
from elo import Node
import asyncio
async def main():
    node = Node('servidor-a', port=7878)
    await node.connect()
    await node.register(agents=['analyst'])
    await node.run()
asyncio.run(main())
"

# Máquina B conecta em A via IP Tailscale
python -c "
from elo import Node
import asyncio
async def main():
    node = Node('servidor-b', port=7878, peers=['100.80.1.50:7878'])
    await node.connect()
    await node.register(agents=['writer'])
    await node.run()
asyncio.run(main())
"
```

## WireGuard puro

Mesmo princípio. Cada máquina com IP privado. Elo conecta via esses IPs.

## Docker

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY py/ /app/py/
RUN pip install /app/py
COPY meu_no.py /app/
EXPOSE 7878
CMD ["python", "/app/meu_no.py"]
```
