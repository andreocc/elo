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

### Tracker privado (descoberta central)

Para malhas com 3+ nós ou nós atrás de NAT/Docker que não expõem porta:

1. Escolha um nó sempre online como **tracker** (ex: VM com Tailscale)
2. Rode o tracker em `examples/python/tracker.py`
3. Todos os outros nós conectam ao tracker via `peers=["IP_DO_TRACKER:7878"]`
4. Qualquer nó descobre os demais via task `discovery`

```
Nó A (Docker, sem Tailscale) → conecta ao → Tracker (VM, Tailscale)
Nó B (notebook)               → conecta ao ──┘
Nó C (qualquer)               → conecta ao ──┘
```

### Setup com tracker

```bash
# Máquina tracker (ex: SAM, IP 100.91.215.113)
pip install elo-node
python examples/python/tracker.py

# Máquina A (cliente)
python -c "
from elo import Node
import asyncio
async def main():
    node = Node('no-a', port=0, peers=['100.91.215.113:7878'])
    await node.connect()
    await node.register(agents=['analyst'])
    await node.run()
asyncio.run(main())
"

# Máquina B descobre A via tracker
python -c "
from elo import Node
import asyncio
async def main():
    node = Node('no-b', port=0, peers=['100.91.215.113:7878'])
    await node.connect()
    await node.register(agents=['writer'])
    await asyncio.sleep(1)
    # Descobre quem tem 'analyst'
    result = await node.send_task('', 'discovery', {})
    print(result.payload)
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

**Importante:** nós Docker atrás de NAT sem port mapping não podem ser alcançados — use o padrão **tracker** (cliente Docker conecta ao tracker, nunca o contrário).
