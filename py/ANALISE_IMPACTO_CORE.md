# Análise de Impacto Técnico — Mudanças no Core do Elo

## 1. Identity Isolation (BREAKING CHANGE)

### Estado Atual

```python
# node.py:47-63
def _load_or_generate_identity() -> EphemeralIdentity:
    seed_path = DEFAULT_DATA_DIR / "identity.seed"
    if seed_path.exists():
        # Carrega persistente SILENCIOSAMENTE
        ...
    return EphemeralIdentity()  # efêmera se não existir
```

```python
# node.py:96 — __init__
self._identity = identity or _load_or_generate_identity()
```

**Comportamento hoje:** `Node("foo")` sem `identity=` tenta carregar `~/.elo/identity.seed`. Se existe, usa identidade persistente. Se não existe, gera efêmera. **Mágica silenciosa.**

### Mudança Proposta

`Node()` sem `identity=` **sempre** gera efêmera. Para ter persistência, o caller precisa passar `identity=load_identity()` explicitamente:

```python
# Antes (funciona, mas implícito):
node = Node("meu-agente")

# Depois (explícito):
from elo import load_identity
identity = load_identity()  # levanta FileNotFoundError se não existir
node = Node("meu-agente", identity=identity)
```

### Impacto Técnico Detalhado

| Aspecto | Impacto |
|---------|---------|
| **Scripts existentes** | Todo script que faz `Node("x")` e depende de identidade persistente **quebra**. Novo `node_id` a cada restart. Perde reputação, permissões, filas. |
| **`_load_or_generate_identity()`** | Função deve ser removida ou renomeada para `_generate_ephemeral()`. |
| **`__init__` (L96)** | Mudar de `self._identity = identity or _load_or_generate_identity()` para `self._identity = identity or EphemeralIdentity()`. |
| **`EphemeralIdentity`** | Classe já existe, funciona perfeitamente. Nenhuma mudança necessária. |
| **`load_identity()`** | Já existe em `elo/security.py`. Retorna `(private_key, None)`. O consumidor precisa extrair a pub key e criar um wrapper — ou `load_identity()` precisa retornar um `EphemeralIdentity` completo. |
| **`security.load_identity()`** | Retorna `(Ed25519PrivateKey, None)` — incompatível com o parâmetro `identity: EphemeralIdentity`. Precisa de adaptador. |
| **Testes** | `TestNodeConstruction.test_default_values` (L137-143) cria `Node("test-node")` sem identity. CONTINUA FUNCIONANDO (identidade efêmera). |
| **`__main__.py`** | `elo init` já gera `identity.seed`. CLI precisa ser atualizada para mostrar como passar `identity=load_identity()`. |

### Arquivos Afetados

| Arquivo | Linhas | Mudança |
|---------|--------|---------|
| `elo/node.py` | 47-63 | Remover `_load_or_generate_identity()`. Substituir por `_generate_ephemeral()` simples. |
| `elo/node.py` | 96 | `identity or EphemeralIdentity()` |
| `elo/security.py` | 96-116 | `load_identity()` deve retornar um `EphemeralIdentity` ou criar factory que devolve `EphemeralIdentity`-like. |
| `elo/__init__.py` | 22, 27 | Exportar helper `load_identity_as_ephemeral()` ou similar. |
| `elo/__main__.py` | 54-74 | CLI `init` e `id` commands. |

### Ordem na Implementação

**Fase 1 — preparação (PRIORIDADE ALTA, fazer primeiro).**
1. Criar `EphemeralIdentity.from_file(key_dir=DEFAULT_KEY_DIR)` em `security.py` — carrega `identity.seed` e devolve `EphemeralIdentity` completo.
2. Remover `_load_or_generate_identity()` de `node.py`.
3. Trocar L96 para `self._identity = identity or EphemeralIdentity()`.
4. Atualizar `__init__.py` exports.

---

## 2. Auto-Reconnect

### Estado Atual

```python
# tcp.py:209-228 — _read_loop
async def _read_loop(self, addr, peer):
    try:
        while ...:
            msg = await peer.recv()
            if msg is None:
                break  # Desconectou — fim. Sem retry.
            ...
    finally:
        peer.close()
        self._peers.pop(addr, None)  # Remove do dicionário
        # Notifica handler com BYE sintético
```

**Zero lógica de reconexão.** Quando `_read_loop` termina (peer desconectou, timeout, erro de leitura), o peer é removido de `_peers` e nunca mais tentamos conectar de volta.

### Mudança Proposta

1. `send_task()` detecta peer desconectado → tenta reconectar
2. `run()` detecta perda de conexão com tracker → tenta reconectar
3. Backoff exponencial: 1s, 2s, 4s, 8s, max 60s

### Análise de Implementação

**Onde detectar desconexão:**

| Ponto de Detecção | Arquivo | Mecanismo |
|-------------------|---------|-----------|
| `_read_loop` termina (finally block) | `tcp.py:220-228` | Já sabemos exatamente quando. |
| `start_heartbeat` marca peer como dead por idle timeout | `tcp.py:350-360` | `HEARTBEAT_IDLE_TIMEOUT` = 90s. |
| `send_to` levanta `ConnectionError` | `tcp.py:40-41` | `PeerConnection.send()` seta `_alive = False`. |
| `send_task` recebe `NO_PEER` ou `SEND_ERROR` | `node.py:266-267` | Result.error do send_task. |

**Estratégia de reconexão:**

```python
# NOVO: Transport level reconnect
class TCPManager:
    _reconnect_backoff: dict[str, ReconnectState] = {}
    
    async def _schedule_reconnect(self, peer_addr: str, hello_payload: dict):
        state = self._reconnect_backoff.get(peer_addr, ReconnectState())
        delay = min(state.attempts * 2, 60)  # 1, 2, 4, 8... max 60
        state.attempts += 1
        await asyncio.sleep(delay)
        result = await self.connect_to_peer(addr, hello_payload=hello_payload)
        if result:
            del self._reconnect_backoff[peer_addr]
```

**Problemas:**

1. **`hello_payload`**: A HELLO carrega caps, interests, tracker visibility, version. Esses dados mudam se o nó fizer `register()` depois. A HELLO precisa ser recriada ou armazenada dinamicamente.
2. **Endereço original**: O peer pode estar num endereço IP:porta volátil (Docker, Tailscale). Reconectar para o mesmo endereço pode falhar sempre se o peer mudou de IP.
3. **Stale vs live**: Se o peer reconecta com IP novo, `_handle_incoming` já detecta o stale peer via `_remove_stale_peer()`. A reconexão outbound pode competir com a inbound.
4. **Tracker reconexão**: Não há um conceito de "tracker connection" distinto no código. O tracker É um peer normal que está no `_peers` dict. Se o tracker cai, sabemos porque `_read_loop` termina, mas não sabemos QUAL peer é o tracker.

### Arquivos Afetados

| Arquivo | Mudança |
|---------|---------|
| `elo/transport/tcp.py` | Adicionar `_reconnect_backoff: dict`, lógica de re-schedule em `_read_loop` finally, método `_schedule_reconnect()`. |
| `elo/transport/tcp.py` | `_remove_from_peers()` (refactor de `finally` block). |
| `elo/node.py` | `_handle_message` BYE detection → gatilho de reconexão. |
| `elo/node.py` | `send_task()` ao receber `SEND_ERROR` / `ConnectionError` → tentar reconnect antes de desistir. |
| `elo/node.py` | `run()` → heartbeat loop verificar se tracker-especific peer se foi. |

---

## 3. Zero-Config Bootstrap

### Estado Atual

```python
# node.py:78-79
peers: list[str] | None = None,
tracker: str = "public",
```

```python
# node.py:175-184 — connect()
hello = hello_msg(...)
for addr in self._initial_peers:
    await self._tcp.connect_to_peer(addr, hello_payload=hello)
```

- `tracker="public"` significa "sou um tracker público" — não "conecte a um tracker público".
- Sem `peers=`, ninguém. Nó fica isolado.

### Mudança Proposta

- Tracker público opcional (ex: `elo.alphaworks.com.br:7878`)
- `Node()` sem `peers=` nem `tracker=` tenta descoberta local via DHT/LAN multicast

### Análise de Implementação

**Tracker público como seed:**
```python
PUBLIC_TRACKER = "elo.alphaworks.com.br:7878"
```

Adicionar lógica em `connect()`:

```python
if not self._initial_peers:
    # Tenta conectar ao tracker público
    try:
        await self._tcp.connect_to_peer(PUBLIC_TRACKER, hello_payload=hello)
    except:
        # Fallback: descoberta local
        ...
```

**Descoberta LAN (sem DHT):**

O protocolo já tem `QUERY` / `QUERY_RESP` com broadcast e TTL. Mas broadcast só funciona para peers já conectados via TCP — não descobre peers na LAN sem configuração prévia.

Opções para descoberta LAN:
1. **UDP Multicast** (239.255.43.21:7879) — envia "alô, alguém na porta 7878?".
   - `asyncio` tem `startup(self, ...)` para UDP.
   - Resposta contém "estou aqui, meu node_id é...".
   - Após resposta, faz TCP connect.
2. **TCP scan local** — tenta conectar em `192.168.1.1-255:7878`.
   - Mais pesado, mas não precisa de UDP.
3. **Usar already existing QUERY broadcast** — mas QUERY só funciona dentro da mesh TCP já formada.

**Solução mais prática:** UDP multicast discovery simples:

```python
# NOVO: elo/transport/discovery.py
MCAST_GRP = "239.255.43.21"
MCAST_PORT = 7879

class Discovery:
    async def start(self):
        # Escuta multicast
        pass
    
    async def announce(self):
        # "elo.node node_id=xxx port=7878"
        pass
```

**DHT Kademlia:** O protocolo já define mensagens DHT (`DHT_PING`, `DHT_FIND_NODE`, etc.) em `protocol.py:38-45` mas **NÃO TEM implementação**. Seria um módulo novo completo (`elo/transport/dht/`). Escopo grande demais para esta fase — deixo como Fase 3.

### Arquivos Afetados (Fase 2 — LAN multicast)

| Arquivo | Mudança |
|---------|---------|
| `elo/transport/discovery.py` | **NOVO** — UDP multicast discovery. |
| `elo/transport/__init__.py` | Exportar `Discovery`. |
| `elo/node.py` | `connect()` — tentar tracker público, fallback LAN discovery. |
| `elo/node.py` | Opcional: `Node(..., discovery=True)` |

---

## 4. Heartbeat Mais Robusto

### Estado Atual

```python
# tcp.py:328-360
async def start_heartbeat(self):
    while not self._shutdown.is_set():
        await asyncio.wait_for(self._shutdown.wait(), timeout=30)
        hb = heartbeat_msg(self._node_id)
        for addr, peer in list(self._peers.items()):
            await peer.send(hb)
            if peer.idle_seconds > self.HEARTBEAT_IDLE_TIMEOUT:  # 90s
                dead.append(addr)
```

**Problemas:**
1. **Heartbeat é envio unilateral** — o nó envia heartbeat aos peers, mas **não verifica se o próprio tracker/peer ainda está vivo do lado de lá**. É baseado em `idle_seconds` (quanto tempo desde o último `recv()` bem-sucedido). Isso funciona, mas é reativo — só detecta morte depois de 90s de inatividade.
2. **Se o heartbeat SEND falha**, o peer é marcado como dead imediatamente. Isso é correto.
3. **Não há heartbeat do tracker para o nó** — tracker pode morrer e o nó só descobre após 90s.

### Mudança Proposta

Se tracker não responder a 3 heartbeats seguidos (90s), considerar desconectado e iniciar reconexão.

### Análise

**Já implementado parcialmente!** O `HEARTBEAT_IDLE_TIMEOUT = 90` (3 * 30s de intervalo) já faz exatamente isso — se o peer não enviar NADA em 90s, é declarado morto.

**Melhorias necessárias:**

1. **Heartbeat bidirecional** — o peer também manda heartbeat. Se não recebemos nada do peer em 90s, dead. (Já implementado via `idle_seconds`.)
2. **Heartbeat request-response** — em vez de apenas enviar heartbeat unilateral, o nó pode pedir confirmação explícita para peers críticos (tracker).

**Proposta concreta:**

```python
# Melhoria no heartbeat:
# 1. Continua enviando heartbeat a cada 30s (já existe)
# 2. Adiciona last_heartbeat_ack: dict[str, float] — quando recebemos ACK do peer
# 3. No start_heartbeat, verifica se tracker-specific peer respondeu
# 4. Se tracker morreu → inicia reconexão (ao invés de só remover)
```

O atual `idle_seconds` já conta como tracker check se o tracker envia heartbeat. Mas **trackers não enviam heartbeat explícito** — a menos que seja um peer conectado. Na prática, qualquer mensagem (QUERY, HELLO, etc.) atualiza `_last_read`. Se o tracker fica quieto por 90s, o peer morre.

**Resumo:** A mudança de heartbeat é **incremental** — o mecanismo básico já existe. Precisa de:
- Gatilho de reconexão quando heartbeat detecta morte (junto com #2)
- Heartbeat mais frequente ou com confirmação explícita (opcional)

### Arquivos Afetados

| Arquivo | Mudança |
|---------|---------|
| `elo/transport/tcp.py` | `start_heartbeat()` — ao remover peer morto, chamar `_schedule_reconnect()`. |

---

## 5. Fallback de Entrega (Pending Queue)

### Estado Atual

```python
# node.py:266-269
return Result.make_error(task_id, "NO_PEER", f"No peer for: {capability}")
```

Se `send_task()` falha por peer offline, **desiste imediatamente**. Task perdida.

### Mudança Proposta

Se `send_task(target, ...)` retorna `NO_PEER`, salvar em fila local e tentar novamente quando reconectar.

### Análise de Implementação

```python
# NOVO: elo/pending_queue.py
@dataclass
class PendingTask:
    target_node: str
    capability: str
    payload: dict
    ttl_s: int
    created_at: float
    retries: int = 0

class PendingQueue:
    def __init__(self):
        self._queue: list[PendingTask] = []
    
    def enqueue(self, target, capability, payload, ttl_s=60):
        self._queue.append(PendingTask(...))
    
    async def flush(self, node: Node) -> int:
        """Tenta reenviar todos os tasks pendentes. 
        Retorna quantos foram enviados com sucesso."""
        sent = 0
        remaining = []
        for task in self._queue:
            result = await node.send_task(...)
            if result.status == "error":
                remaining.append(task)
            else:
                sent += 1
        self._queue = remaining
        return sent
```

**Trigger de flush:**
- Quando um peer conecta (`on_hello` / `on_hello_ack`)
- No heartbeat loop (a cada 30s)

**Problemas:**
1. **Deadlock potencial**: Se o pending queue tenta reenviar e o destino ainda está offline, o flush gera muitos `NO_PEER` em cascata. Precisa de backoff por task.
2. **Persistência**: A fila é volátil (memória). Se o processo morre, tasks pendentes são perdidas. Para persistência, salvar em `~/.elo/pending/` JSON.
3. **Ordem**: FIFO simples pode não ser ideal — tasks mais recentes podem ter mais chance de sucesso.

### Arquivos Afetados

| Arquivo | Mudança |
|---------|---------|
| `elo/pending_queue.py` | **NOVO** — `PendingQueue` class. |
| `elo/node.py` | `send_task()` — ao receber `NO_PEER`, salvar na fila em vez de desistir. |
| `elo/node.py` | Novo método `_flush_pending()` chamado em `connect()` e periodicamente. |
| `elo/node.py` | `run()` — agendar flush periódico. |

---

## Ordem de Implementação Recomendada

```
FASE 1 (P0 — BREAKING CHANGE):
  Identity Isolation
    ⤷ security.py: add EphemeralIdentity.from_file()
    ⤷ node.py: remove _load_or_generate_identity()
    ⤷ node.py: __init__ identity = identity or EphemeralIdentity()
    ⤷ __main__.py: update CLI
    ⤷ __init__.py: update exports
  ⚠️ QUEBRA TODOS OS SCRIPTS EXISTENTES
  ⏱ 2-3h

FASE 2 (P0 — Funcionalidade):
  Heartbeat + Auto-Reconnect (integrados)
    ⤷ tcp.py: _schedule_reconnect() com backoff exponencial
    ⤷ tcp.py: _read_loop → reconnect trigger
    ⤷ tcp.py: start_heartbeat → reconnect trigger
    ⤷ node.py: send_task → tentar reconnect antes de desistir
  ⏱ 4-6h

FASE 3 (P1):
  Pending Queue (Fallback de entrega)
    ⤷ pending_queue.py: NOVO
    ⤷ node.py: send_task → enqueue on NO_PEER
    ⤷ node.py: _flush_pending()
  ⏱ 3-4h

FASE 4 (P1):
  Zero-Config Bootstrap
    ⤷ discovery.py: NOVO (UDP multicast)
    ⤷ node.py: connect() → try public tracker → fallback LAN
    ⤷ tracker público opcional (elo.alphaworks.com.br)
  ⏱ 4-6h

FASE 5 (P2 — Futuro):
  DHT Kademlia completo
    ⤷ elo/transport/dht/ (novo módulo)
    ⤷ Substitui ou complementa multicast LAN
  ⏱ 8-16h
```

## Matriz de Dependências

```
Identity Isolation ──► (nenhuma) ──► Pode ser feito primeiro
         │
         ▼
Heartbeat + Reconnect ──► Pending Queue (precisa de reconnect para re-enviar)
         │
         ▼
Pending Queue ──► Zero-Config Bootstrap (mais peers = mais chance de entrega)
         │
         ▼
Zero-Config ──► DHT (aprimoramento da descoberta)
```

**Nota:** Heartbeat + Reconnect NÃO depende de Identity Isolation, mas idealmente fazemos o breaking change primeiro para minimizar retrabalho em scripts de teste.

## Riscos Técnicos

| Risco | Probabilidade | Mitigação |
|-------|--------------|-----------|
| Reconexão infinita (loop) | Média | Limitar tentativas (max 5) ou backoff até 60s com reset. |
| Race condition reconexão inbound vs outbound | Alta | Já existe `_remove_stale_peer()`. Usar lock por node_id. |
| Pending queue cresce sem limite | Média | `max_size` configurável. TTL por task (ex: 5 min). |
| UDP multicast não funciona no Windows/Docker | Média | Fallback para TCP scan local ou arquivo `~/.elo/known_peers`. |
| Tracker público SPAM/DDoS | Alta | Rate limiting já existe. Adicionar allowlist no tracker público. |
