# Especificação do Protocolo Elo v1

## 1. Identidade

Cada nó possui par ed25519. A chave pública é o `node_id`.

```
node_id = base64_urlsafe(ed25519_pubkey_raw)   # 32 bytes → ~43 chars
```

## 2. Transporte

TCP direto entre peers. Porta padrão: 7878.

### Framing
```
[4 bytes: payload length (big-endian uint32)][JSON payload (UTF-8)]
```
Tamanho máximo: 1 MB.

## 3. Mensagens

### 3.1 HELLO
```json
{
  "type": "hello",
  "node_id": "tTPsbs8NjQux...",
  "caps": {"agents": [{"name": "analyst", "model": "gpt-4o"}], "tools": [], "models": []},
  "interests": ["analyst"],
  "tracker": "public",
  "version": "0.4.0"
}
```

### 3.2 HELLO_ACK
Mesmo schema do HELLO. Resposta ao handshake.

### 3.3 QUERY
```json
{"type": "query", "capability": "analyst", "id": "a1b2c3d4", "ttl": 5}
```

### 3.4 QUERY_RESP
```json
{"type": "query_resp", "id": "a1b2c3d4", "nodes": [{"node_id": "...", "addr": "10.0.1.5:7878"}]}
```

### 3.5 TASK
```json
{
  "type": "task", "id": "uuid", "target": "...", "caller": "...",
  "capability": "analyst", "payload": {},
  "ttl_s": 60, "signature": "base64_ed25519",
  "protocol": "elo.v1", "timestamp": 1712345678
}
```

Assinatura cobre todos os campos exceto `signature`, em JSON canônico (sorted keys).

### 3.6 RESULT
```json
{"type": "result", "id": "uuid", "status": "success", "payload": {}, "protocol": "elo.v1"}
```
Status: `"success"`, `"error"`, `"timeout"`.

### 3.7 INTEREST_UPDATE
```json
{"type": "interest_update", "interests": ["analyst", "code-gen"]}
```

### 3.8 HEARTBEAT
```json
{"type": "heartbeat", "node_id": "...", "ts": 1712345678}
```
Intervalo: 30s. Timeout: 90s (3 intervalos).

### 3.9 BYE
```json
{"type": "bye"}
```

## 4. Interest-Based Routing

Cada nó mantém InterestTable:
- `local_caps`: capabilities que oferece
- `local_interests`: capabilities que procura
- `forwarding`: capability → peers conhecidos

**Roteamento:**
1. Forwarding hit → envia direto
2. Miss → broadcast QUERY{capability, ttl=5}
3. QUERY_RESP → conecta ao peer → envia TASK

## 5. Segurança

- Assinatura ed25519 em toda TASK (canonical JSON)
- `verify_peers=True` por padrão
- WireGuard/Tailscale recomendado para criptografia de rede
