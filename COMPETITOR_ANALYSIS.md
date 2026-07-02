# Análise de Concorrentes

## 1. Synadia Agent Protocol (NATS-native)

| Item | Detalhe |
|------|---------|
| **Autor** | Synadia (criadores do NATS) |
| **Data** | Maio 2026 |
| **Stack** | NATS Core |
| **Tipo** | Protocolo sobre NATS para agentes |
| **GitHub** | github.com/synadia-ai/synadia-agent-sdk-docs |
| **SDKs** | TypeScript, Python (referência), NATS CLI |

**O que faz:** Define três responsabilidades sobre NATS:
- **Discovery** via NATS micro service (`$SRV.PING.agents`)
- **Conversation** via streaming JSON chunks (response/status/query)
- **Liveness** via heartbeats (`agents.hb.{agent}.{owner}.{name}`)

**Diferença do Elo:** Synadia Agent Protocol é um protocolo de aplicação — define *como* agentes se comunicam (formato de chunks, tipos de mensagem, fluxo de query). Elo é infraestrutura de transporte — define *como* nós se encontram e trocam mensagens, sem ditar formato de conteúdo.

**Risco para Elo:** ALTO — é o projeto mais próximo do Elo, usa a mesma base (NATS), e tem o aval da Synadia. Porém, concentra-se no protocolo de conversação, não no registro de capacidades nem no gerenciamento de nós.

---

## 2. ANP — Agent Network Protocol

| Item | Detalhe |
|------|---------|
| **Autor** | Comunidade (white paper arXiv Jul/2025) |
| **Stack** | HTTP/HTTPS, DID, JSON-LD, OpenAPI |
| **Tipo** | Protocolo de aplicação em 3 camadas |
| **Site** | agent-network-protocol.com |

**Arquitetura:**
1. **Identity & Secure Communication Layer** — DID (W3C), ECDHE para e2e encryption
2. **Meta-Protocol Layer** — negociação dinâmica de protocolos entre agentes via NL
3. **Application Protocol Layer** — ADP (descrição), Agent Discovery (bem-known + busca)

**Diferença do Elo:** ANP é um protocolo de aplicação completo com negociação dinâmica via NL, DID complexo e schema JSON-LD. Elo foca em infraestrutura de transporte simples (NATS + NKEYS). ANP roda sobre HTTP — Elo sobre NATS (pub/sub nativo).

**Risco para Elo:** MÉDIO — ANP está em white paper, sem implementação madura. A complexidade do meta-protocol negotiation com code generation é ambiciosa demais.

---

## 3. A2A — Agent-to-Agent Protocol (Google)

| Item | Detalhe |
|------|---------|
| **Autor** | Google |
| **Data** | Abril 2025 (v1.0 2026) |
| **Stack** | JSON-RPC 2.0 sobre HTTP(S), SSE |
| **Tipo** | Protocolo de colaboração entre agentes |
| **Site** | a2a-protocol.org |

**Arquitetura:**
- Descoberta via **Agent Cards** (arquivo JSON em `/.well-known/agent.json`)
- Comunicação síncrona (JSON-RPC), streaming (SSE) e push
- Focado em agentes opacos (não se importa com implementação interna)
- Extensível via URI de extensão

**Diferença do Elo:** A2A é HTTP-based (request-response tradicional). Elo é pub/sub baseado em NATS com streaming nativo. A2A resolve colaboração entre agentes de empresas diferentes (interop B2B). Elo resolve comunicação dentro de uma malha de agentes própria.

**Risco para Elo:** MÉDIO — A2A é o padrão mais forte para interoperabilidade entre agentes de organizações diferentes. Não compete diretamente com Elo (infra privada vs protocolo público).

---

## 4. ACP — Agent Communication Protocol (IBM)

| Item | Detalhe |
|------|---------|
| **Autor** | IBM Research / Linux Foundation |
| **Data** | Março 2025 |
| **Stack** | HTTP REST (POST/GET/PUT/DELETE) |
| **Tipo** | Protocolo de comunicação estruturado |

**Arquitetura:**
- **Brokered**: Agent Clients → ACP Servers (registry) → ACP Agents
- Mapeia comunicação em verbos HTTP (POST=criar task, GET=status, PUT=atualizar, DELETE=cancelar)
- 4 camadas (definidas no arXiv paper)

**Diferença do Elo:** ACP usa HTTP REST síncrono com broker centralizado. Elo é pub/sub descentralizado com NATS. ACP exige um servidor ACP rodando; Elo só precisa do NATS cluster.

**Risco para Elo:** BAIXO — ACP é protocolo HTTP com broker. Mais pesado, menos flexível. IBM backing mas sem muito tração.

---

## 5. MCP — Model Context Protocol (Anthropic)

| Item | Detalhe |
|------|---------|
| **Autor** | Anthropic |
| **Data** | 2024 (v1.0 2026) |
| **Stack** | JSON-RPC sobre transporte (stdio/HTTP) |
| **Tipo** | Agente → Ferramenta (não agente→agente) |

**O que faz:** Conecta LLMs a ferramentas e fontes de dados. Não resolve comunicação entre agentes.

**Diferença do Elo:** MCP é agente→tool. Elo é agente→agente. Complementares, não concorrentes.

**Risco para Elo:** BAIXO — domínios diferentes.

---

## 6. EOS — Entity Orchestration System

| Item | Detalhe |
|------|---------|
| **Autor** | orizone-io (GitHub) |
| **Stack** | Schema-driven, protocolo + runtime |
| **Tipo** | Orquestração de LLMs e serviços |

**Observação:** O repositório original não foi encontrado em pesquisa direta. Pode ter sido renomeado ou movido. Os resultados apontam para EOS blockchain (EOSIO), EOS robotics (UNC), e EOS OS (embodied intelligence) — nenhum deles relacionado a agentes de IA.

**Risco para Elo:** BAIXO — não encontramos o projeto específico. Se existiu, não tem presença pública forte.

---

## 7. EOS Blockchain / EOSIO | Arista EOS

Não são concorrentes diretos:
- EOS Blockchain = smart contracts
- Arista EOS = network OS
- E.OS (UNC Robotics) = orquestração de laboratório

**Risco para Elo:** NULO — domínios completamente diferentes.

---

## Matriz de Posicionamento

```
                    A2A ─── ANP
                   /      \
         HTTP-based        Schema-heavy
         /                     \
    ACP ──── HTTP REST ──── JSON-LD/DID
                                    \
                                     Meta-protocol
                                        NL negotiation
                                              |
                                         (complexidade alta)

                Elo ─── NATS-based ──── Simples, leve
                         │
              Synadia Protocol ─── mesma stack, foco diferente
```

| Projeto | Stack | Foco | Concorrência |
|---------|-------|------|-------------|
| **Synadia** | NATS | Protocolo de conversação | Alta — mesma stack |
| **ANP** | HTTP/DID | Protocolo de aplicação 3 camadas | Média |
| **A2A** | HTTP/JSON-RPC | Interoperabilidade entre agentes | Média |
| **ACP** | HTTP REST | Protocolo de comunicação | Baixa |
| **MCP** | JSON-RPC | Agente→Ferramenta | Nula |
| **EOS** | Desconhecido | Orquestração | Nula |

## Diferenciais do Elo

1. **Primeiro a usar NATS KV como registry** com TTL por heartbeat — zero lógica de limpeza
2. **Separação clara entre transporte e aplicação** — o protocolo não dita formato de conteúdo
3. **Identidade criptográfica por nó** (NKEYS) sem necessidade de PKI ou DID complexo
4. **Suporte nativo a assíncrono** via JetStream (filas, retry, exactly-once)
5. **Leve o suficiente para rodar em edge/embedded** — dependência única: NATS client lib

## Riscos

- **Synadia Agent Protocol** pode evoluir e cobrir o mesmo espaço — acompanhar de perto
- **Fragmentação de protocolos** — mercado pode convergir para A2A ou ANP como padrão
- **Elo depende do ecossistema NATS** — se NATS perder tração, Elo perde junto
