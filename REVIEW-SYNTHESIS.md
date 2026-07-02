# Elo — Síntese das Revisões

> Saruman (24 Jun 2026) + Navalhas (01 Jul 2026) → Plano unificado

---

## O que mudou desde a revisão do Saruman

| Saruman (24 Jun) | Estado em 01 Jul | Resolução |
|------------------|-----------------|-----------|
| "NATS é dependência operacional" | ✅ Resolvido | NATS removido do core. P2P sobre TCP direto. NATS virou plugin opcional |
| "Registry node_id-based, sem capability-routing" | ✅ Resolvido | InterestTable + LocalTracker + QUERY broadcast substituem NATS KV |
| "docs/specs/ vazio" | ✅ Resolvido | auth-schema, message-schema, registry-schema, elo-protocol — todos preenchidos |
| "Identidade efêmera como padrão gera surpresa" | ⚠️ Ainda pendente | `EphemeralIdentity()` é o default. `python -m elo init` existe mas é manual |
| "Validar 2 nós WAN" | ❌ Ainda pendente | Nunca testado. Ambos reviews concordam: é o teste que separa conceito de realidade |
| "Dual SDK Go + Python" | ⚠️ Congelado | Go SDK tem crypto + transport P2P básico. Node.go ainda usa NATS. Congelado até Python estável |
| "Criar skill Hermes elo-node" | ❌ Não feito | Exemplo `hermes-integration.py` existe mas não é skill carregável |

---

## O que as duas revisões concordam

### Concordância #1: Validar em WAN real é o próximo passo crítico

```
Saruman:  "É o teste que separa conceito de realidade"  (item 5, Recomendações)
v0.3:     "Nunca testado em WAN real"                   (funcional, item 5)
```

**Ambos dizem:** sem 3 nós em máquinas diferentes trocando tasks, o Elo é teoria.

### Concordância #2: A base conceitual é sólida

```
Saruman:  "Elo acerta no essencial: ser pequeno, ser óbvio"     (Veredito)
v0.3:     "Arquitetura conceitual é sólida e minimalista"        (Resumo final)
```

**Ambos dizem:** TCP + ed25519 + HELLO é a escolha certa. O problema não é o design — é a execução.

### Concordância #3: Menos é mais

```
Saruman:  "3 conceitos. 1 bucket KV. 1 identidade"             (§2.1)
v0.3:     "4 conceitos: TCP, ed25519, HELLO, InterestTable"     (Occam)
```

**Ambos dizem:** o diferencial do Elo é ter menos conceitos que os concorrentes. Cada feature nova precisa justificar sua existência.

### Concordância #4: Identidade deveria ser persistente por default

```
Saruman:  "Inverter o default. Se ~/.elo/identity.seed existe → usa. 
          Workers de produção devem sempre ter identidade persistente."  (item 3)
v0.3:     (Implícito — não tratado diretamente, mas o EphemeralIdentity 
          como default é consistente com a análise de simplicidade)
```

**Saruman diz:** inverter. **v0.3 diz:** manter efêmero (KISS). Este é o único ponto de discordância real entre as revisões.

---

## O que o Saruman viu que a v0.3 não cobriu

| Ponto Saruman | Status | Ação |
|---------------|--------|------|
| "publish-by-capability" — publicar em tópico por capacidade, não por node_id | ⚠️ Não implementado | O QUERY broadcast + InterestTable resolve isso indiretamente, mas a sugestão de publicar direto em `elo.v1.cap.<capability>` como atalho é válida |
| "Benchmark de latência — find_peer + request-reply vs publish-by-capability" | ❌ Não feito | 0 benchmarks. Ambos reviews pedem números |
| "Criar skill Hermes elo-node" | ❌ Não feito | 50 linhas, valor imediato |
| "Runbook com modos dev/single-node/cluster" | ⚠️ Parcial | RUNBOOK atualizado para P2P mas sem modos explícitos |

---

## O que a v0.3 viu que o Saruman não viu

| Ponto v0.3 | Por que o Saruman não viu |
|-----------|--------------------------|
| 2 bugs bloqueantes (read loop outbound + result matching) | Código foi reescrito depois da revisão do Saruman (NATS → P2P) |
| DHT Kademlia é YAGNI | Não existia na época do Saruman (só NATS KV) |
| Task queue é YAGNI | Não existia |
| 825 linhas em node.py | O node.py do Saruman tinha 511 linhas (NATS). O atual tem 825 (P2P + DHT + queue) |
| 3 afirmações falsas no README | O README do Saruman era o v0.1 (NATS). O atual foi reescrito mas manteve claims não verificáveis |
| 12 navalhas filosóficas | Análise feita depois |

---

## Síntese final: o plano unificado

Do que **ambas** as revisões concordam + o que cada uma acrescenta:

```
FASE 1 — CORRIGIR (4h)
├── Bug #1: read loop em conexões outbound       [v0.3]
├── Bug #2: _wait_for_result reentrante           [v0.3]
└── Bug #3: identidade padrão → verifica disco    [Saruman #3 + v0.3 implícito]
    Se ~/.elo/identity.seed existe → carrega
    Se não existe → gera efêmera com warning

FASE 2 — CORTAR (2h)
├── Remover DHT (dht.py, 459 linhas)              [v0.3 Bellard]
├── Remover TaskQueue (queue.py, 233 linhas)      [v0.3 Bellard]
├── Remover NATS plugin + discovery.py            [v0.3 Bellard]
├── Remover E2E (campo encrypted + stubs)         [v0.3 Bellard]
├── Remover mDNS do core → plugin                 [v0.3 Bellard]
├── Remover event log persistente → ring buffer   [v0.3 Bellard]
├── Congelar Go SDK                               [v0.3 Bellard]
└── Simplificar CLI (só status + serve)           [v0.3 Bellard]

FASE 3 — VALIDAR (2h)
├── 3 máquinas com Tailscale                       [Saruman #5 + v0.3 Semana 2]
├── 3 agentes (echo, analyst, writer)              [Saruman #5 + v0.3 Semana 2]
├── 1 comando que prova: assert status=='success'  [v0.3 Popper rule]
└── Medir latência: HELLO + TASK + RESULT          [Saruman #6]

FASE 4 — PUBLICAR (1h)
├── Atualizar README: só claims falseáveis         [v0.3 Popper]
├── Publicar no PyPI (`pip install elo-node`)      [POSITIONING #5]
└── Gravar demo: 2 nós trocando tasks              [Saruman #5]
```

**Tempo total: ~9h**

---

## O que NÃO entra agora (adiado para depois de uso real)

| Feature | Quem pediu | Quando reconsiderar |
|---------|-----------|-------------------|
| DHT Kademlia | v0.3 implementou, Bellard cortou | Quando houver 50+ peers na mesh |
| Task queue com retry | v0.3 implementou, Bellard cortou | Quando um agente real pedir |
| E2E encryption | v0.3 implementou mas nunca funcionou | Quando key exchange for implementada |
| Go SDK completo | Saruman elogiou dual SDK | Quando Python estiver estável 3+ meses |
| Hermes skill | Saruman recomendou | Quando Hermes precisar de integração real |
| Benchmark formal | Ambos pediram | Fase 3 cobre medição básica |
| mDNS no core | v0.3 moveu pra plugin | Quando alguém pedir LAN discovery |

---

## Regra de ouro (de agora em diante)

> **"Toda feature listada no README deve ter um comando de 1 linha que prova que funciona."** — Popper's Razor, aplicada ao Elo

Exemplo:
```bash
# Claim: "Agentes se descobrem e trocam tasks"
python -c "
import asyncio
from elo import Node
async def t():
    a = Node('a', port=0); b = Node('b', port=0)
    await a.connect(); await b.connect()
    await a.register(agents=['echo'])
    # b connects to a, sends task, gets result
    ...
    assert result.status == 'success'
asyncio.run(t())
"
```

Se esse comando não passa, a feature não existe.
