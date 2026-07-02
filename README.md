# Elo 🔗

**Malha P2P de mensagens para agentes de IA. Um processo. Uma porta. Uma chave.**

Elo é uma mesh peer-to-peer: cada nó é um servidor TCP que se conecta diretamente a outros nós. Sem NATS, sem Kafka, sem Kubernetes. Apenas agentes conversando entre si.

## Prova de 1 linha

```bash
python -c "
import asyncio
from elo import Node
from elo.security import EphemeralIdentity
async def t():
    a=Node('a',port=0,identity=EphemeralIdentity()); b=Node('b',port=0,identity=EphemeralIdentity())
    await a.connect(); await b.connect(); await a.register(agents=['echo'])
    async def h(task): return {'echo':task.payload}
    a.on_task(h)
    from elo.transport import hello_msg
    await b._tcp.connect_to_peer(f'localhost:{a.port}',hello_payload=hello_msg(b.node_id,{},{},'public','0.4.0'))
    asyncio.create_task(a.run()); await __import__('asyncio').sleep(0.2)
    r=await b.send_task('','echo',{'msg':'ping'})
    assert r.status=='success' and r.payload['echo']['msg']=='ping'
    print('OK')
asyncio.run(t())
"
```

## Filosofia

- **Zero infraestrutura.** TCP direto entre peers. Sem servidor central.
- **Identidade criptográfica.** Cada nó tem uma chave ed25519 — o `node_id` é a chave pública.
- **Não é um framework.** Agentes existentes não precisam ser reescritos.
- **Interest-based routing.** Peers anunciam o que têm e o que procuram.

## Componentes

| Componente | Linhas | Descrição |
|-----------|--------|-----------|
| **Elo Node** | ~300 | Servidor TCP + cliente P2P |
| **Interest Table** | 135 | Roteamento por capability |
| **Local Tracker** | 97 | Registro local de agentes/tools |
| **Wire Protocol** | 167 | Framed JSON sobre TCP |
| **Security** | 347 | ed25519 + X25519 + AES-256-GCM |

## Início rápido

```bash
cd py && pip install -e .
```

```python
import asyncio
from elo import Node

async def main():
    node = Node("meu-agente", port=7878)
    await node.connect()
    await node.register(agents=["echo-agent"], tools=["ping"])

    @node.on_task
    async def handle(task):
        print(f"[task] {task.capability}: {task.payload}")
        return {"echo": task.payload, "from": node.node_id}

    await node.run()

asyncio.run(main())
```

## CLI

```bash
python -m elo status       # Node ID, hash, chaves
python -m elo id           # Apenas o node_id
python -m elo init         # Gerar identidade persistente (~/.elo/)
python -m elo serve        # Iniciar nó interativo
```

## Licença

MIT — ver [LICENSE](LICENSE).
