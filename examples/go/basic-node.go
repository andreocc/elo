package main

// Elo Node — exemplo funcional usando o SDK Go.
//
// Uso:
//   docker run -d --name nats -p 4222:4222 nats:2.10-alpine
//   cd go && go run ../examples/go/basic-node.go

import (
	"log"
	"os"
	"os/signal"

	"github.com/xalq/elo"
)

func main() {
	node := elo.NewNode("exemplo-go", "nats://localhost:4222")
	if err := node.Connect(); err != nil {
		log.Fatal(err)
	}
	defer node.Disconnect()

	node.Register(elo.RegisterOpts{
		Agents: []elo.AgentCap{{Name: "echo-agent"}},
		Tools:  []elo.ToolCap{{Name: "ping"}},
	})

	node.OnTask(func(task elo.Task) any {
		log.Printf("[task] %s: %v", task.Capability, task.Payload)
		return map[string]any{
			"echo":         task.Payload,
			"processed_by": node.NodeID(),
		}
	})

	// Graceful shutdown
	sig := make(chan os.Signal, 1)
	signal.Notify(sig, os.Interrupt)
	go func() {
		<-sig
		node.Disconnect()
	}()

	log.Printf("[elo] running | node=%s", node.NodeID())
	node.Run()
}
