package elo

import (
	"encoding/json"
	"fmt"
	"math/rand"
	"strings"

	"github.com/nats-io/nats.go"
)

const (
	registryBucket      = "elo-registry"
	registryTTLSeconds  = 90
)

// Discovery manages peer discovery through the NATS KV registry.
type Discovery struct {
	js nats.JetStreamContext
	kv nats.KeyValue
}

// EnsureBucket creates or retrieves the elo-registry KV bucket.
func (d *Discovery) EnsureBucket() (nats.KeyValue, error) {
	if d.kv != nil {
		return d.kv, nil
	}

	kv, err := d.js.KeyValue(registryBucket)
	if err == nil {
		d.kv = kv
		return kv, nil
	}

	kv, err = d.js.CreateKeyValue(&nats.KeyValueConfig{
		Bucket: registryBucket,
		TTL:    registryTTLSeconds * 1_000_000_000, // nanos
	})
	if err != nil {
		return nil, fmt.Errorf("create kv bucket: %w", err)
	}

	d.kv = kv
	return kv, nil
}

// RegisterNode writes node metadata to the registry.
func (d *Discovery) RegisterNode(nodeID string, info NodeInfo) error {
	kv, err := d.EnsureBucket()
	if err != nil {
		return err
	}
	data, _ := json.Marshal(info)
	_, err = kv.Put("node:"+nodeID, data)
	return err
}

// RegisterCapabilities writes node capabilities to the registry.
func (d *Discovery) RegisterCapabilities(nodeID string, caps Capabilities) error {
	kv, err := d.EnsureBucket()
	if err != nil {
		return err
	}
	data, _ := json.Marshal(caps)
	_, err = kv.Put("caps:"+nodeID, data)
	return err
}

// Unregister removes a node from the registry.
func (d *Discovery) Unregister(nodeID string) error {
	kv, err := d.EnsureBucket()
	if err != nil {
		return err
	}
	_ = kv.Delete("node:" + nodeID)
	_ = kv.Delete("caps:" + nodeID)
	return nil
}

// ListNodes returns all online nodes with their metadata.
func (d *Discovery) ListNodes() (map[string]NodeInfo, error) {
	kv, err := d.EnsureBucket()
	if err != nil {
		return nil, err
	}

	keys, err := kv.Keys()
	if err != nil {
		return nil, err
	}

	nodes := make(map[string]NodeInfo)
	for _, key := range keys {
		if !strings.HasPrefix(key, "node:") {
			continue
		}
		entry, err := kv.Get(key)
		if err != nil || entry == nil {
			continue
		}
		var info NodeInfo
		if err := json.Unmarshal(entry.Value(), &info); err != nil {
			continue
		}
		nodeID := strings.TrimPrefix(key, "node:")
		nodes[nodeID] = info
	}
	return nodes, nil
}

// ListCapabilities returns all node capabilities.
func (d *Discovery) ListCapabilities() (map[string]Capabilities, error) {
	kv, err := d.EnsureBucket()
	if err != nil {
		return nil, err
	}

	keys, err := kv.Keys()
	if err != nil {
		return nil, err
	}

	capsMap := make(map[string]Capabilities)
	for _, key := range keys {
		if !strings.HasPrefix(key, "caps:") {
			continue
		}
		entry, err := kv.Get(key)
		if err != nil || entry == nil {
			continue
		}
		var caps Capabilities
		if err := json.Unmarshal(entry.Value(), &caps); err != nil {
			continue
		}
		nodeID := strings.TrimPrefix(key, "caps:")
		capsMap[nodeID] = caps
	}
	return capsMap, nil
}

// FindByCapability finds a node with the desired capability.
// Strategy "random" (default) or "first".
func (d *Discovery) FindByCapability(capability, strategy string) (string, error) {
	allCaps, err := d.ListCapabilities()
	if err != nil {
		return "", err
	}

	var matches []string
	for nodeID, caps := range allCaps {
		for _, a := range caps.Agents {
			if a.Name == capability {
				matches = append(matches, nodeID)
				break
			}
		}
		for _, t := range caps.Tools {
			if t.Name == capability {
				matches = append(matches, nodeID)
				break
			}
		}
		for _, m := range caps.Models {
			if m.Name == capability {
				matches = append(matches, nodeID)
				break
			}
		}
	}

	if len(matches) == 0 {
		return "", fmt.Errorf("no node with capability %q", capability)
	}
	if strategy == "random" {
		return matches[rand.Intn(len(matches))], nil
	}
	return matches[0], nil
}

// GetNodeInfo retrieves metadata for a specific node.
func (d *Discovery) GetNodeInfo(nodeID string) (*NodeInfo, error) {
	kv, err := d.EnsureBucket()
	if err != nil {
		return nil, err
	}
	entry, err := kv.Get("node:" + nodeID)
	if err != nil {
		return nil, err
	}
	if entry == nil {
		return nil, fmt.Errorf("node %q not found", nodeID)
	}
	var info NodeInfo
	if err := json.Unmarshal(entry.Value(), &info); err != nil {
		return nil, err
	}
	return &info, nil
}
