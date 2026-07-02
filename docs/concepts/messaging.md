# Message Patterns

Elo suporta padrões de mensagem sobre TCP P2P.

## 1. Request-Reply (Unicast)

**Uso**: tasks síncronas

```python
result = await node.send_task("peer_addr", "analyst", {"query": "..."}, ttl_s=30)
# Aguarda RESULT do peer
```

## 2. Broadcast (QUERY)

**Uso**: descoberta de capabilities

```python
# Internamente, quando o Node não conhece um peer para a capability:
# Broadcast QUERY{capability, ttl=5} → peers respondem QUERY_RESP
# Conecta ao peer descoberto → envia TASK direta

result = await node.send_task("", "analyst", {"query": "..."})
```

## 3. Fire-and-Forget

**Uso**: heartbeats, eventos, notificações

```python
await node.publish_event("node.online")
# Sem resposta. Sem garantia de entrega.
```

## 4. Async Task

**Uso**: tasks sem espera de resultado

```python
task_id = await node.send_task_async("peer_addr", "analyst", {"job": "..."})
# Não espera resposta. task_id para tracking.
```
