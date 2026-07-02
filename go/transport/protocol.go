package transport

import (
	"encoding/binary"
	"encoding/json"
	"fmt"
	"io"
)

// Frame format: [4-byte big-endian length][JSON payload]
const (
	FrameHeaderSize  = 4
	MaxPayloadSize   = 1 << 20 // 1 MB
)

// Message types
const (
	MsgHello          = "hello"
	MsgHelloAck       = "hello_ack"
	MsgQuery          = "query"
	MsgQueryResp      = "query_resp"
	MsgInterestUpdate = "interest_update"
	MsgTask           = "task"
	MsgResult         = "result"
	MsgEvent          = "event"
	MsgHeartbeat      = "heartbeat"
	MsgBye            = "bye"
)

// EncodeFrame encodes a message map into a framed JSON payload.
func EncodeFrame(msg map[string]any) ([]byte, error) {
	data, err := json.Marshal(msg)
	if err != nil {
		return nil, fmt.Errorf("encode: %w", err)
	}
	if len(data) > MaxPayloadSize {
		return nil, fmt.Errorf("payload too large: %d bytes", len(data))
	}
	frame := make([]byte, FrameHeaderSize+len(data))
	binary.BigEndian.PutUint32(frame[:FrameHeaderSize], uint32(len(data)))
	copy(frame[FrameHeaderSize:], data)
	return frame, nil
}

// ReadFrame reads a single framed message from a reader.
func ReadFrame(r io.Reader) (map[string]any, error) {
	header := make([]byte, FrameHeaderSize)
	if _, err := io.ReadFull(r, header); err != nil {
		return nil, fmt.Errorf("read header: %w", err)
	}
	length := binary.BigEndian.Uint32(header)
	if length > MaxPayloadSize {
		return nil, fmt.Errorf("invalid payload length: %d", length)
	}
	data := make([]byte, length)
	if _, err := io.ReadFull(r, data); err != nil {
		return nil, fmt.Errorf("read payload: %w", err)
	}
	var msg map[string]any
	if err := json.Unmarshal(data, &msg); err != nil {
		return nil, fmt.Errorf("unmarshal: %w", err)
	}
	return msg, nil
}

// Message builders

func HelloMsg(nodeID string, caps, interests any, tracker, version string) map[string]any {
	return map[string]any{
		"type":      MsgHello,
		"node_id":   nodeID,
		"caps":      caps,
		"interests": interests,
		"tracker":   tracker,
		"version":   version,
	}
}

func HelloAckMsg(nodeID string, caps, interests any, tracker string) map[string]any {
	return map[string]any{
		"type":      MsgHelloAck,
		"node_id":   nodeID,
		"caps":      caps,
		"interests": interests,
		"tracker":   tracker,
	}
}

func QueryMsg(capability, queryID string, ttl int) map[string]any {
	return map[string]any{
		"type":       MsgQuery,
		"capability": capability,
		"id":         queryID,
		"ttl":        ttl,
	}
}

func QueryRespMsg(queryID string, nodes []map[string]string) map[string]any {
	return map[string]any{
		"type":  MsgQueryResp,
		"id":    queryID,
		"nodes": nodes,
	}
}

func TaskMsg(taskID, target, caller, capability string, payload any) map[string]any {
	return map[string]any{
		"type":       MsgTask,
		"id":         taskID,
		"target":     target,
		"caller":     caller,
		"capability": capability,
		"payload":    payload,
		"protocol":   "elo.v1",
	}
}

func ResultMsg(taskID, status string, payload any, err map[string]string) map[string]any {
	m := map[string]any{
		"type":     MsgResult,
		"id":       taskID,
		"status":   status,
		"protocol": "elo.v1",
	}
	if payload != nil {
		m["payload"] = payload
	}
	if err != nil {
		m["error"] = err
	}
	return m
}

func HeartbeatMsg(nodeID string) map[string]any {
	return map[string]any{
		"type":    MsgHeartbeat,
		"node_id": nodeID,
	}
}

func ByeMsg() map[string]any {
	return map[string]any{"type": MsgBye}
}
