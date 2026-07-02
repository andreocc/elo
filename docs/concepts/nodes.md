# Elo Node Concepts

## O que é um Elo Node?

Um processo Python que abre servidor TCP (porta 7878) e se identifica com chave ed25519.

```
Elo Node ─── hospeda ─── Agente(s)
  │                        │
  │── identity ed25519     │── capability name
  │── TCP server :7878     │── model binding
  │── interest table       │── tool bindings
  │── local tracker        │
```

## Ciclo de vida

```
[connect] → abre TCP server → conecta a peers manuais
[register] → popula tracker local → broadcast INTEREST_UPDATE
[run] → escuta tasks → heartbeat → gerencia peers
[disconnect] → BYE para peers → fecha conexões
```

## Identidade

- **node_id** = base64 da chave pública ed25519
- Chave privada assina toda task enviada
- Peers verificam assinatura (`verify_peers=True`)

### Persistente vs Efêmera

| Tipo | Comportamento |
|------|-------------|
| Persistente | Carrega de `~/.elo/identity.seed` se existir |
| Efêmera | Gerada nova se não houver seed |

```bash
python -m elo init    # gera identidade persistente
python -m elo status  # mostra node_id
```

## Tracker

Cada nó publica seu próprio tracker — registro local de agentes, modelos, ferramentas.

| Modo | HELLO | QUERY de desconhecidos |
|------|-------|----------------------|
| `public` | Envia todas as capabilities | Responde com todas |
| `private` | Envia vazio | Não responde |

```python
node = Node("servidor", port=7878, tracker="private",
            allowlist=["Pabc123...", "Pdef456..."])
```

## Heartbeat

Cada peer envia HEARTBEAT a cada 30s. Timeout de 90s remove peer da tabela.

## Peer Exchange

Peers aprendem sobre outros via:
1. **Manual**: lista `--peers` fornecida pelo usuário
2. **HELLO**: handshake troca capabilities e interests
3. **QUERY_RESP**: respostas revelam endereços de peers
