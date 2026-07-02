---
reviewer: Saruman (Hermes Agent)
date: 2026-06-24
context: Primeira análise de arquitetura e código
version: pre-release (v1 protocol, SDKs funcionais)
---

# Revisão Saruman — Elo 🔗

> Opinião técnica baseada na leitura completa do repositório: README, ARCHITECTURE, POSITIONING, COMPETITOR_ANALYSIS, RUNBOOK, código Python (node.py, types.py, security.py, discovery.py), exemplo Hermes, docs de conceito.

---

## 1. O Que Elo É

Uma camada de transporte distribuída para agentes de IA sobre NATS. Não é framework, não é protocolo de aplicação. É o substrato que permite qualquer nó (Hermes, XWP, script Python, CLI Go) se encontrar e trocar mensagens com identidade criptográfica.

Três conceitos. Um bucket KV. Uma identidade NKEY ed25519.

---

## 2. O Que Está Excelente

### 2.1 Minimalismo Cirúrgico

POSITIONING.md acerta em cheio. A tabela comparativa é honesta:

| Dimensão | ANP | A2A | Synadia | Elo |
|----------|-----|-----|---------|-----|
| Conceitos no protocolo | 12+ | 8+ | 6+ | **3** |
| Dependências para rodar | HTTP + DID | HTTP | NATS cluster | **NATS cluster** |
| Arquivos de config | Múltiplos | Agent Card JSON | Envelope + metadados | **1 NKEY** |
| Linhas para nó funcional | ~200+ | ~200+ | ~80 | **~40** |

NATS KV com TTL para auto-cleanup de nós offline é a decisão mais inteligente do projeto. Zero lógica de limpeza, zero goroutines esquecidas, zero bugs de stale state.

### 2.2 Separação Transporte vs Aplicação

Isso é o que diferencia Elo do Synadia Agent Protocol. Synadia define formato de conversação (chunks tipados, query/response/status). Elo só entrega a mensagem — quem decide o significado é o agente.

Isso permite que um mesmo nó fale Elo internamente e A2A/ANP externamente via Gateway. A separação é limpa e proposital.

### 2.3 Implementação Sólida (Python SDK)

O código é limpo, sem firula, com testes. Destaques:

- **node.py (511 linhas):** Conexão/reconexão NATS nativa, heartbeat com jitter, graceful shutdown que remove do registry, cache de peers com TTL
- **security.py (347 linhas):** ed25519 pra identidade, X25519 ECDHE + AES-256-GCM pra E2E, HKDF pra derivação de chave. Crypto correto sem reinventar roda
- **types.py (128 linhas):** Dataclasses limpas, serialização explícita (sem magia), schemas auto-documentados no código

Dependência única: `nats-py` + `cryptography` (biblioteca padrão da indústria).

### 2.4 Dual SDK (Go + Python)

Raro em projeto early-stage. Mostra que o design já considerou runtime diversity desde o início. A interface entre os dois SDKs é o protocolo NATS — não uma ponte HTTP ou RPC.

### 2.5 Runbook Completo

Troubleshooting table, comandos nats CLI, recovery procedures. Pra um projeto pré-release, isso é fora da curva.

---

## 3. O Que Precisa de Atenção

### 3.1 NATS É Dependência Operacional

"Só docker run" funciona em dev. Em produção, NATS cluster com auth NKEY + TLS + persistência JetStream exige operação dedicada. Não é leve como SQLite ou um arquivo JSON.

Pra stack que já roda Docker (XWP, Hermes gateway), é viável — mas não é zero-overhead. Recomendação: documentar explicitamente os modos de operação (dev / single-node / cluster) com os trade-offs de cada um.

### 3.2 Registry é node_id-based, Não Capability-Routing

`find_by_capability()` faz scan linear no KV bucket. Funciona para 10 nós. Para 1000 nós, NATS KV não escala como roteador de mensagens — precisaria de um índice separado ou subjects por capacidade.

**Sugestão:** Além de `find_peer()`, oferecer publish por capacidade como padrão alternativo:

```
elo.v1.cap.<capability>.<task_id>
```

Isso delega o roteamento para o próprio NATS (que faz isso nativamente via subscriptions), eliminando o round-trip extra de KV lookup + publish.

### 3.3 Identidade Efêmera Como Padrão Gera Surpresa

`EphemeralIdentity` é o padrão. Cada restart do processo gera um novo `node_id`. Ótimo para dev/teste. Em produção, tasks pendentes no momento do restart perdem o destino porque o node_id mudou.

**Sugestão:** Inverter o default. Se `~/.elo/identity.seed` existe → usa. Se não existe → gera efêmera e loga warning. Workers de produção devem sempre ter identidade persistente.

### 3.4 docs/specs/ Vazio

Os schemas (message-schema.md, auth-schema.md, registry-schema.md) são placeholders. Sem spec formal, o protocolo é definido por implementação — o Python SDK é a referência de facto.

Isso bloqueia:
- Implementação em outras linguagens sem ler o código Python
- Auditoria de segurança independente
- Garantia de compatibilidade entre SDKs (Go vs Python)

**Sugestão:** Escrever a spec antes de publicar. A POSITIONING.md promete que cabe em uma página. Se cumprir, o projeto ganha credibilidade instantânea.

### 3.5 Discovery Tem Latência de 1 Round-Trip

O fluxo atual:
```
caller → find_peer() [KV lookup] → recebe node_id → publish no tópico do node_id [request-reply]
```

Isso introduz latência extra em cada task síncrona. Para cenários onde 50ms importa (trading, tempo real), isso soma.

**Mitigação:** Cache de peers com TTL (já implementado em node.py!). O cache de 5 ciclos de heartbeat reduz o problema a casos de cold start.

---

## 4. Posicionamento no Ecossistema Atual

### 4.1 Concorrência Real: Synadia Protocol

É o único competidor na mesma stack (NATS) com o mesmo público (agentes de IA). Synadia define protocolo de *conversação* (como os agentes trocam chunks tipados). Elo define protocolo de *transporte* (como os nós se encontram).

**Risco:** Synadia pode evoluir para cobrir descoberta e registro. Acompanhar de perto.

### 4.2 Concorrência Indireta: A2A (Google)

A2A resolve interoperabilidade *entre organizações* (agentes de empresas diferentes conversando). Elo resolve comunicação *dentro de uma malha própria*.

São complementares, não concorrentes. O Gateway opcional do Elo pode falar A2A para fora.

### 4.3 Não-Concorrentes

- **ANP:** Muita complexidade (DID, JSON-LD, meta-protocol negotiation via NL). White paper sem implementação madura.
- **ACP (IBM):** HTTP REST com broker centralizado. Mais pesado, menos flexível.
- **MCP (Anthropic):** Agente → ferramenta. Domínio diferente.

---

## 5. Integração com a Stack XALQ

| Sistema | O que é hoje | O que Elo adiciona |
|---------|-------------|-------------------|
| **Hermes (Saruman)** | Agente central, delegate_task para subagentes | Virar nó Elo que XWP e outros agentes descobrem e chamam via capacidade |
| **XWP** | 8 containers isolados, sem API pública | Cada worker pode ser nó Elo registrado com capacidades específicas |
| **Forge (AgentWork)** | Motor de governança A2A (6 camadas authz, audit trail, escalation) | Elo como *transporte* por baixo do A2A que o Forge já fala. Orthogonais |
| **InvGate** | API-only, sem agente | Nó Elo bridge expondo capacidades: search-ticket, create-catalog, get-sla |
| **Novos agentes** | Integração custom uma por uma | Qualquer runtime que importar a lib já participa da malha |

**Pulo do gato:** Elo não compete com o Forge. Forge faz governança (quem pode fazer o quê, audit trail). Elo faz transporte (como a mensagem chega). Eles funcionam juntos.

---

## 6. Recomendações

### Imediatas (pré-1.0)

1. **Escrever os specs** — message-schema.md, auth-schema.md, registry-schema.md. Se cabe em uma página, como a POSITIONING promete, o projeto ganha credibilidade e permite implementações independentes.

2. **Inverter default de identidade** — persistente primeiro, efêmera como fallback com warning. Workers de produção precisam de node_id estável.

3. **Adicionar publish-by-capability** — além de `find_peer()`, permitir publicar em `elo.v1.cap.<capability>.<id>` e deixar NATS rotear.

### Curto Prazo

4. **Criar um skill Hermes "elo-node"** — skill que transforma o Hermes em nó Elo automaticamente. 50 linhas, valor imediato. O exemplo `hermes-integration.py` existe mas não é carregável como skill.

5. **Validar com 2 nós em servidores diferentes** — o COMPETITOR_ANALYSIS lista isso como pendente (#3). É o teste que separa conceito de realidade.

6. **Benchmark de latência** — `find_peer()` + request-reply vs publish-by-capability. Números concretos para guiar a escolha de padrão.

---

## 7. Veredito

Elo acerta no essencial: **ser pequeno, ser óbvio, não competir com o que já existe.**

Em um mercado onde ANP quer resolver tudo com JSON-LD + DID + meta-protocol negotiation (12 conceitos antes de mandar a primeira mensagem), Elo é o equivalente a NATS vs Kafka — dez por cento do que os outros fazem, cem por cento do necessário.

O risco real não é técnico. É adoção. Uma malha de 2 nós é trivial. Uma malha de 20 nós exige que todos os agentes implementem o SDK.

Se o Hermes for o primeiro nó e o XWP o segundo, já valeu — porque a alternativa é glue code manual que quebra na primeira mudança de topologia.

> _"Menos é mais. Sempre foi."_ — POSITIONING.md
