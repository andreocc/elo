# Message Schema Specification

## Formato geral

Toda mensagem Elo é JSON, com campo obrigatório `protocol` identificando a versão.

### Campos comuns

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `protocol` | string | sim | Versão do protocolo: `"elo.v1"` |
| `type` | string | sim | Tipo da mensagem |
| `id` | string | sim | UUID v4 único |
| `timestamp` | int | sim | Unix timestamp (segundos) |
| `signature` | string | não | Assinatura ed25519 do payload |

### Campos por tipo

#### `type: "task"`

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `target` | string | node_id alvo |
| `caller` | string | node_id remetente |
| `capability` | string | Nome da capacidade desejada |
| `payload` | any | Conteúdo da tarefa |
| `ttl_s` | int | Timeout em segundos |

#### `type: "result"`

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `status` | string | `"success"` / `"error"` / `"timeout"` |
| `payload` | any | Resultado (se success) |
| `error` | object | `{code, message}` (se error) |

#### `type: "event"`

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `event_type` | string | `"task.completed"`, `"node.online"`, `"node.offline"`, `"capability.changed"` |
| `data` | any | Dados do evento |
