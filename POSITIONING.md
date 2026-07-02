# Posicionamento Elo v0.4

## Por que Elo existe

Construir sistemas multi-agente exige escolher entre frameworks que acoplam o agente ao transporte, ou glue code manual que quebra na primeira mudança de topologia.

## Três Abordagens

### Opção A: Framework Tudo-Em-Um (LangGraph, CrewAI, AutoGen)
Tudo integrado, mas o agente fica preso ao framework.

### Opção B: Protocolo de Aplicação (ANP, A2A, Synadia Protocol)
Definem *como* agentes falam. Resolvem metade do problema.

### Opção C: Elo — Camada de Transporte Minimalista
**1 processo. 1 porta TCP. 1 chave ed25519.**

## Definição de Pronto

- Um nó conecta, registra capacidades e descobre peers com < 30 linhas
- Nenhum nó precisa de configuração além da porta TCP + lista de peers
- Nó offline some da mesh automaticamente (heartbeat timeout 90s)
- Spec do protocolo cabe em uma página
- Zero dependências além de `cryptography`

## Plano de Implementação

1. ✅ SDK Python
2. ⬜ SDK Go (congelado — foco em Python primeiro)
3. ✅ Validar 2 nós trocando tasks
4. ⬜ Validar WAN real (3+ máquinas)
5. ⬜ Publicar PyPI

## Comparação Essencial

| Dimensão | ANP | A2A | Synadia | **Elo** |
|----------|-----|-----|---------|---------|
| Conceitos no protocolo | 12+ | 8+ | 6+ | **4** (TCP, ed25519, HELLO, InterestTable) |
| Dependências | HTTP + DID | HTTP | NATS cluster | **0** (só cryptography) |
| Arquivos de config | Múltiplos | Agent Card JSON | Envelope + metadados | **0** (identidade = chave) |
| Linhas para nó funcional | ~200+ | ~200+ | ~80 | **~25** |
| Auto-cleanup de nós offline | ❌ | ❌ | Sim | **Sim (heartbeat)** |

## Fabrice Bellard na Alma

| Princípio | Como Elo aplica |
|-----------|----------------|
| **Occam** | TCP já resolve. Descoberta? HELLO + InterestTable. Auth? ed25519. |
| **KISS** | Spec cabe em uma página. Hello World tem 25 linhas. |
| **YAGNI** | Sem meta-protocolo, sem DHT, sem DID, sem JSON-LD. |
| **Bellard** | Um binário, zero servidores extras. Complexidade não existe. |

Menos é mais. Sempre foi.
