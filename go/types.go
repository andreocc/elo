package elo

import (
	"crypto/rand"
	"encoding/hex"
	"time"
)

// ── Capabilities ────────────────────────────────────────────

type AgentCap struct {
	Name        string `json:"name"`
	Description string `json:"description,omitempty"`
	Model       string `json:"model,omitempty"`
}

type ModelCap struct {
	Name     string `json:"name"`
	Provider string `json:"provider,omitempty"`
	Context  int    `json:"context,omitempty"`
}

type ToolCap struct {
	Name        string `json:"name"`
	Description string `json:"description,omitempty"`
	Version     string `json:"version,omitempty"`
}

type Capabilities struct {
	Agents []AgentCap `json:"agents"`
	Models []ModelCap `json:"models"`
	Tools  []ToolCap  `json:"tools"`
}

// ── Node Info ───────────────────────────────────────────────

type NodeInfo struct {
	Name      string            `json:"name"`
	Version   string            `json:"version"`
	StartedAt string            `json:"started_at"`
	Status    string            `json:"status"`
	PublicKey string            `json:"public_key,omitempty"`
	NatsURL   string            `json:"nats_url,omitempty"`
	Labels    map[string]string `json:"labels,omitempty"`
}

// ── Messages ────────────────────────────────────────────────

// Task represents an Elo v1 task request.
type Task struct {
	Protocol   string `json:"protocol"`
	Type       string `json:"type"`
	ID         string `json:"id"`
	Timestamp  int64  `json:"timestamp"`
	Target     string `json:"target"`
	Caller     string `json:"caller"`
	Capability string `json:"capability"`
	Payload    any    `json:"payload"`
	TTLSeconds int    `json:"ttl_s"`
	Signature  string `json:"signature,omitempty"`   // ed25519 signature
	Encrypted  bool   `json:"encrypted,omitempty"`    // E2E encryption flag
}

// Result represents an Elo v1 task result.
type Result struct {
	Protocol string         `json:"protocol"`
	Type     string         `json:"type"`
	ID       string         `json:"id"`
	Status   string         `json:"status"` // "success" | "error" | "timeout"
	Payload  any            `json:"payload,omitempty"`
	Error    *ResultError   `json:"error,omitempty"`
}

type ResultError struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}

// Event represents an Elo v1 event notification.
type Event struct {
	Protocol  string `json:"protocol"`
	Type      string `json:"type"`
	ID        string `json:"id"`
	Timestamp int64  `json:"timestamp"`
	EventType string `json:"event_type"`
	Data      any    `json:"data"`
}

// ── Helpers ─────────────────────────────────────────────────

func newTaskID() string {
	b := make([]byte, 16)
	_, _ = rand.Read(b)
	return hex.EncodeToString(b)
}

func unixNow() int64 {
	return time.Now().UTC().Unix()
}

// ResultSuccess creates a success result.
func ResultSuccess(taskID string, payload any) Result {
	return Result{
		Protocol: "elo.v1",
		Type:     "result",
		ID:       taskID,
		Status:   "success",
		Payload:  payload,
	}
}

// NewResultError creates an error result.
func NewResultError(taskID, code, message string) Result {
	return Result{
		Protocol: "elo.v1",
		Type:     "result",
		ID:       taskID,
		Status:   "error",
		Error: &ResultError{
			Code:    code,
			Message: message,
		},
	}
}
