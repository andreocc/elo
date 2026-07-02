package elo

import (
	"encoding/json"
	"fmt"
	"log"
	"math/rand"
	"time"

	"github.com/nats-io/nats.go"
)

// TaskHandler is the callback signature for task processing.
type TaskHandler func(task Task) any

// Node is an Elo mesh node — NATS client with managed lifecycle.
type Node struct {
	name              string
	natsURL           string
	version           string
	heartbeatInterval time.Duration
	labels            map[string]string

	nc         *nats.Conn
	js         nats.JetStreamContext
	discovery  *Discovery
	nodeID     string
	caps       Capabilities
	taskHandler TaskHandler

	shutdownCh chan struct{}
	hbDone     chan struct{}
}

// NodeOption is a functional option for Node.
type NodeOption func(*Node)

// WithVersion sets the node version.
func WithVersion(v string) NodeOption {
	return func(n *Node) { n.version = v }
}

// WithHeartbeatInterval sets the heartbeat interval.
func WithHeartbeatInterval(d time.Duration) NodeOption {
	return func(n *Node) { n.heartbeatInterval = d }
}

// WithLabels sets arbitrary labels on the node.
func WithLabels(l map[string]string) NodeOption {
	return func(n *Node) { n.labels = l }
}

// NewNode creates a new Elo Node.
func NewNode(name, natsURL string, opts ...NodeOption) *Node {
	n := &Node{
		name:              name,
		natsURL:           natsURL,
		version:           "0.1.0",
		heartbeatInterval: 30 * time.Second,
		labels:            make(map[string]string),
		shutdownCh:        make(chan struct{}),
		hbDone:            make(chan struct{}),
	}
	for _, opt := range opts {
		opt(n)
	}
	return n
}

// ── Lifecycle ──────────────────────────────────────────────

// Connect connects to the NATS cluster and initializes the registry.
func (n *Node) Connect() error {
	nc, err := nats.Connect(n.natsURL,
		nats.Name(n.name),
		nats.Timeout(10*time.Second),
		nats.ReconnectWait(2*time.Second),
		nats.MaxReconnects(-1),
	)
	if err != nil {
		return fmt.Errorf("nats connect: %w", err)
	}
	n.nc = nc

	js, err := nc.JetStream()
	if err != nil {
		return fmt.Errorf("jetstream: %w", err)
	}
	n.js = js

	n.discovery = &Discovery{js: js}
	if _, err := n.discovery.EnsureBucket(); err != nil {
		return fmt.Errorf("ensure bucket: %w", err)
	}

	n.nodeID = fmt.Sprintf("P%s-%x", n.name, time.Now().UnixNano()%0xFFFFFF)
	log.Printf("[elo] connected | node=%s id=%s nats=%s", n.name, n.nodeID, n.natsURL)
	return nil
}

// Disconnect performs graceful shutdown: unregisters and drains.
func (n *Node) Disconnect() error {
	close(n.shutdownCh)
	<-n.hbDone // wait for heartbeat goroutine

	if n.discovery != nil {
		_ = n.discovery.Unregister(n.nodeID)
	}

	if n.nc != nil {
		n.nc.Drain()
		n.nc = nil
	}

	log.Printf("[elo] disconnected | node=%s", n.name)
	return nil
}

// ── Registration ───────────────────────────────────────────

// RegisterOpts groups registration options by category.
type RegisterOpts struct {
	Agents      []AgentCap
	Models      []ModelCap
	Tools       []ToolCap
}

// Register registers this node's capabilities in the mesh.
func (n *Node) Register(opts RegisterOpts) error {
	if n.discovery == nil {
		return fmt.Errorf("node not connected")
	}

	n.caps = Capabilities{
		Agents: opts.Agents,
		Models: opts.Models,
		Tools:  opts.Tools,
	}

	info := NodeInfo{
		Name:      n.name,
		Version:   n.version,
		StartedAt: time.Now().UTC().Format(time.RFC3339),
		Status:    "online",
		Labels:    n.labels,
	}

	if err := n.discovery.RegisterNode(n.nodeID, info); err != nil {
		return err
	}
	if err := n.discovery.RegisterCapabilities(n.nodeID, n.caps); err != nil {
		return err
	}

	log.Printf("[elo] registered | agents=%d models=%d tools=%d",
		len(opts.Agents), len(opts.Models), len(opts.Tools))
	return nil
}

// ── Handlers ───────────────────────────────────────────────

// OnTask sets the task handler callback.
func (n *Node) OnTask(handler TaskHandler) {
	n.taskHandler = handler
}

// ── Messaging ──────────────────────────────────────────────

// SendTask sends a synchronous task (request-reply) to another node.
func (n *Node) SendTask(targetNode, capability string, payload any, ttl time.Duration) (*Result, error) {
	if n.nc == nil {
		return nil, fmt.Errorf("node not connected")
	}

	task := Task{
		Protocol:   "elo.v1",
		Type:       "task",
		ID:         newTaskID(),
		Timestamp:  unixNow(),
		Target:     targetNode,
		Caller:     n.nodeID,
		Capability: capability,
		Payload:    payload,
		TTLSeconds: int(ttl.Seconds()),
	}

	taskJSON, _ := json.Marshal(task)
	subject := fmt.Sprintf("elo.v1.task.%s.%s", targetNode, task.ID)

	msg, err := n.nc.Request(subject, taskJSON, ttl)
	if err != nil {
		return nil, fmt.Errorf("request: %w", err)
	}

	var result Result
	if err := json.Unmarshal(msg.Data, &result); err != nil {
		return nil, fmt.Errorf("unmarshal result: %w", err)
	}
	return &result, nil
}

// SendTaskAsync sends an async task via JetStream.
func (n *Node) SendTaskAsync(targetNode, capability string, payload any) (string, error) {
	if n.nc == nil {
		return "", fmt.Errorf("node not connected")
	}

	task := Task{
		Protocol:   "elo.v1",
		Type:       "task",
		ID:         newTaskID(),
		Timestamp:  unixNow(),
		Target:     targetNode,
		Caller:     n.nodeID,
		Capability: capability,
		Payload:    payload,
	}

	taskJSON, _ := json.Marshal(task)
	subject := fmt.Sprintf("elo.v1.task.async.%s", targetNode)
	err := n.nc.Publish(subject, taskJSON)
	return task.ID, err
}

// PublishEvent publishes an async event notification.
func (n *Node) PublishEvent(eventType, targetNode string, data any) error {
	if n.nc == nil {
		return fmt.Errorf("node not connected")
	}

	event := Event{
		Protocol:  "elo.v1",
		Type:      "event",
		ID:        newTaskID(),
		Timestamp: unixNow(),
		EventType: eventType,
		Data:      data,
	}

	eventJSON, _ := json.Marshal(event)
	if targetNode == "" {
		targetNode = n.nodeID
	}
	subject := fmt.Sprintf("elo.v1.event.%s.%s", targetNode, eventType)
	return n.nc.Publish(subject, eventJSON)
}

// ── Discovery ──────────────────────────────────────────────

// DiscoverPeers returns all online nodes.
func (n *Node) DiscoverPeers() (map[string]NodeInfo, error) {
	if n.discovery == nil {
		return nil, fmt.Errorf("node not connected")
	}
	return n.discovery.ListNodes()
}

// FindPeer finds a node with the given capability.
func (n *Node) FindPeer(capability string) (string, error) {
	if n.discovery == nil {
		return "", fmt.Errorf("node not connected")
	}
	return n.discovery.FindByCapability(capability, "random")
}

// ── Run Loop ───────────────────────────────────────────────

// Run starts the main loop: subscribes to tasks and publishes heartbeats.
// It blocks until Disconnect() is called.
func (n *Node) Run() error {
	if n.nc == nil {
		return fmt.Errorf("node not connected — call Connect() first")
	}

	// Subscribe to tasks
	taskSubj := fmt.Sprintf("elo.v1.task.%s.>", n.nodeID)
	_, err := n.nc.Subscribe(taskSubj, n.handleTask)
	if err != nil {
		return fmt.Errorf("subscribe tasks: %w", err)
	}
	log.Printf("[elo] listening on %s", taskSubj)

	// Subscribe to events
	eventSubj := fmt.Sprintf("elo.v1.event.%s.>", n.nodeID)
	_, err = n.nc.Subscribe(eventSubj, n.handleEvent)
	if err != nil {
		return fmt.Errorf("subscribe events: %w", err)
	}
	log.Printf("[elo] listening on %s", eventSubj)

	// Heartbeat goroutine
	go n.heartbeatLoop()

	// Online event
	_ = n.PublishEvent("node.online", "", nil)

	log.Printf("[elo] running | node=%s (%s)", n.name, n.nodeID)

	// Block until shutdown
	<-n.shutdownCh
	return nil
}

// ── internal ───────────────────────────────────────────────

func (n *Node) handleTask(msg *nats.Msg) {
	var task Task
	if err := json.Unmarshal(msg.Data, &task); err != nil {
		log.Printf("[elo] bad task: %v", err)
		endResult := NewResultError("unknown", "BAD_REQUEST", "invalid json")
		respJSON, _ := json.Marshal(endResult)
		_ = msg.Respond(respJSON)
		return
	}

	log.Printf("[elo] task received | id=%s capability=%s", task.ID, task.Capability)

	var result Result
	if n.taskHandler != nil {
		payload := n.taskHandler(task)
		result = ResultSuccess(task.ID, payload)
	} else {
		result = ResultSuccess(task.ID, map[string]string{"message": "no handler registered"})
	}

	respJSON, _ := json.Marshal(result)
	_ = msg.Respond(respJSON)
}

func (n *Node) handleEvent(msg *nats.Msg) {
	var event Event
	if err := json.Unmarshal(msg.Data, &event); err != nil {
		return
	}
	log.Printf("[elo] event received | type=%s", event.EventType)
}

func (n *Node) heartbeatLoop() {
	defer close(n.hbDone)

	for {
		select {
		case <-n.shutdownCh:
			return
		case <-time.After(n.heartbeatInterval):
		}

		if n.nc == nil {
			continue
		}

		// Update KV entries
		if n.discovery != nil {
			info := NodeInfo{
				Name:    n.name,
				Version: n.version,
				Status:  "online",
				Labels:  n.labels,
			}
			_ = n.discovery.RegisterNode(n.nodeID, info)
			_ = n.discovery.RegisterCapabilities(n.nodeID, n.caps)
		}

		// Publish heartbeat
		hb := map[string]any{
			"ts":          time.Now().Unix(),
			"instance_id": n.nodeID,
			"interval_s":  n.heartbeatInterval.Seconds(),
		}
		hbJSON, _ := json.Marshal(hb)
		_ = n.nc.Publish("elo.v1.hb."+n.nodeID, hbJSON)

		// Jitter ±10%
		jitter := time.Duration(float64(n.heartbeatInterval) * 0.1 * (rand.Float64()*2 - 1))
		time.Sleep(jitter)
	}
}

// ── Accessors ──────────────────────────────────────────────

// NodeID returns this node's identifier.
func (n *Node) NodeID() string { return n.nodeID }

// Name returns this node's name.
func (n *Node) Name() string { return n.name }
