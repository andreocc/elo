# Security Model

## 1. Identidade (ed25519)

`node_id = base64_urlsafe(ed25519_pubkey)`

- Chave privada nunca trafega na rede
- `node_id` é verificável: assinatura prova posse da chave privada
- Carrega de `~/.elo/identity.seed` ou gera efêmera

## 2. Autenticidade (assinatura ed25519)

Toda task é assinada com chave privada do caller. Receptor (se `verify_peers=True`) verifica.

**Canonical JSON**: payload serializado com sorted keys, sem espaços.

## 3. Rede (Tailscale/WireGuard — recomendado)

| Camada | Protege |
|--------|---------|
| WireGuard | Tráfego entre máquinas |
| ed25519 | Quem enviou a mensagem |

## 4. Ameaças

| Ameaça | Mitigação |
|--------|-----------|
| Peer fingindo ser outro | Assinatura ed25519 — `node_id` é a chave pública |
| Mensagem adulterada | Assinatura cobre o payload |
| Peer malicioso | Tracker private + allowlist |
| Eavesdropping | Tailscale (WireGuard) |
| Negação de serviço | TCP backlog + heartbeat timeout |
