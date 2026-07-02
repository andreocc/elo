# Quickstart Guide

## 5 minutos para seu primeiro nó

### 1. Instalar
```bash
cd py && pip install -e .
```

### 2. Verificar identidade
```bash
python -m elo status
```

### 3. Rodar exemplo
```bash
python examples/python/simple-node.py
```

### 4. Testar com outro nó
```bash
python -c "
import asyncio
from elo import Node
from elo.security import EphemeralIdentity
async def t():
    a=Node('a',port=0,identity=EphemeralIdentity()); b=Node('b',port=0,identity=EphemeralIdentity())
    await a.connect(); await b.connect(); await a.register(agents=['echo'])
    @a.on_task
    async def h(task): return {'echo':task.payload}
    from elo.transport import hello_msg
    await b._tcp.connect_to_peer(f'localhost:{a.port}',hello_payload=hello_msg(b.node_id,{},{},'public','0.4.0'))
    asyncio.create_task(a.run()); await asyncio.sleep(0.2)
    r=await b.send_task('','echo',{'msg':'ping'})
    print(f'status={r.status} payload={r.payload}')
    assert r.status=='success'
asyncio.run(t())
"
```

### 5. CLI
```bash
python -m elo status    # Node ID, hash, chaves
python -m elo serve     # Iniciar nó interativo
python -m elo init      # Identidade persistente
```
