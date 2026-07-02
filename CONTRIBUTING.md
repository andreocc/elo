# Contribuindo

## Convenções

- **Commits**: conventional commits (`feat:`, `fix:`, `docs:`, `refactor:`)
- **Branch**: `feat/<nome>`, `fix/<nome>`, `docs/<nome>`
- **PR**: descrição clara do que muda + por que + como testar

## Protocolo

Mudanças no protocolo (`specs/elo-protocol.md`) exigem:
1. Atualizar o campo `version` no schema
2. Garantir backward compatibility com versões anteriores
3. Adicionar entry no changelog do protocolo

## Testes

```bash
# Python — unitários
cd py && pip install -e ".[dev]" && pytest

# Python — integração (requer NATS rodando)
cd py && NATS_URL=nats://localhost:4222 pytest -m integration

# Go — unitários
cd go && go test ./...

# Go — integração (requer NATS rodando)
cd go && go test -tags=integration ./...
```

## Licença

MIT
