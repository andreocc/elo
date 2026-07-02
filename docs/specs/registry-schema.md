# Registry Schema — Tracker Local

Cada nó publica seu próprio tracker via HELLO/HELLO_ACK.

## Caps (capabilities)

```json
{
  "agents": [{"name": "analyst", "description": "Análise", "model": "gpt-4o"}],
  "models": [{"name": "gpt-4o", "provider": "openai", "context": 128000}],
  "tools": [{"name": "web-search", "description": "Busca", "version": "1.0"}]
}
```

## Interests

```json
["analyst", "code-gen", "web-search"]
```

## Visibilidade

| Modo | HELLO caps | QUERY response |
|------|-----------|----------------|
| `public` | Envia todas | Responde com todas |
| `private` | Envia vazio | Só para allowlist |

## Distribuição

1. **HELLO/HELLO_ACK**: caps + interests no handshake
2. **INTEREST_UPDATE**: broadcast quando caps/interests mudam
3. **QUERY/QUERY_RESP**: descoberta sob demanda
