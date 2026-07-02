# Auth Schema — Identidade e Assinatura

## Geração

```bash
python -m elo init    # gera ~/.elo/identity.seed + identity.x25519
python -m elo id      # mostra node_id
```

## Ed25519 Key Pair

```
Chave privada: 32 bytes (seed)
Chave pública:  32 bytes
node_id:        base64_urlsafe(pubkey)  — ~43 caracteres
```

## Assinatura

1. Remove campo `signature` do payload
2. Canonical JSON: `json.dumps(payload, sort_keys=True, separators=(",", ":"))`
3. `ed25519_sign(private_key, canonical_bytes)`
4. Anexa assinatura em base64

## Persistência

```
~/.elo/
├── identity.seed    — chave privada ed25519 (PKCS#8 PEM)
└── identity.x25519  — chave privada X25519 (reservada para E2E futuro)
```
