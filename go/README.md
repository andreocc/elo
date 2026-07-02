# Elo Node — SDK Go v0.2

```bash
go get github.com/xalq/elo
```

## Uso rápido (P2P)

```go
package main

import (
    "log"
    "os"
    "os/signal"

    "github.com/xalq/elo"
)

func main() {
    node := elo.NewNode("meu-agente", "localhost:7878")
    if err := node.Connect(); err != nil {
        log.Fatal(err)
    }
    defer node.Disconnect()

    node.Register(elo.RegisterOpts{
        Agents: []elo.AgentCap{{Name: "analyst", Description: "Análise"}},
        Tools:  []elo.ToolCap{{Name: "web-search"}},
    })

    node.OnTask(func(task elo.Task) any {
        log.Printf("Recebi task: %s", task.Capability)
        return map[string]string{"result": "ok"}
    })

    go func() {
        sig := make(chan os.Signal, 1)
        signal.Notify(sig, os.Interrupt)
        <-sig
        node.Disconnect()
    }()

    log.Fatal(node.Run())
}
```

## Dependências

- `github.com/nats-io/nats.go` — para plugin NATS (opcional)
- `golang.org/x/crypto` — criptografia

## Transport

O módulo `transport/` contém a implementação P2P (TCP + protocolo wire).
