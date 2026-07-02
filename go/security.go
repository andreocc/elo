package elo

// Security module — NKEYS, signing, and end-to-end encryption.
// Uses ed25519 for signatures, X25519 + AES-256-GCM for E2E encryption.

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/ed25519"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"sort"

	"golang.org/x/crypto/curve25519"
	"golang.org/x/crypto/hkdf"
)

// ── Key Generation ──────────────────────────────────────────

// GenerateKeyPair generates an ed25519 key pair and returns
// the seed (32 bytes) and public key.
func GenerateKeyPair() (seed, publicKey []byte, err error) {
	pub, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		return nil, nil, fmt.Errorf("generate ed25519: %w", err)
	}
	// The seed is the first 32 bytes of the private key
	seed = priv.Seed()
	return seed, pub, nil
}

// PublicKeyFromSeed derives the public key from an ed25519 seed.
func PublicKeyFromSeed(seed []byte) ed25519.PublicKey {
	return ed25519.NewKeyFromSeed(seed).Public().(ed25519.PublicKey)
}

// NodeIDFromPubKey converts an ed25519 public key to a node ID (base64 URL-safe).
func NodeIDFromPubKey(pub ed25519.PublicKey) string {
	return base64.RawURLEncoding.EncodeToString(pub)
}

// PubKeyFromNodeID decodes a node ID back to an ed25519 public key.
func PubKeyFromNodeID(nodeID string) (ed25519.PublicKey, error) {
	raw, err := base64.RawURLEncoding.DecodeString(nodeID)
	if err != nil {
		return nil, fmt.Errorf("decode node id: %w", err)
	}
	if len(raw) != ed25519.PublicKeySize {
		return nil, fmt.Errorf("invalid public key size: %d", len(raw))
	}
	return ed25519.PublicKey(raw), nil
}

// GenerateX25519KeyPair generates an X25519 key pair for ECDHE.
func GenerateX25519KeyPair() (private, public []byte, err error) {
	priv := make([]byte, 32)
	if _, err := rand.Read(priv); err != nil {
		return nil, nil, fmt.Errorf("generate x25519: %w", err)
	}
	// Clamp the private key
	priv[0] &= 248
	priv[31] &= 127
	priv[31] |= 64

	pub, err := curve25519.X25519(priv, curve25519.Basepoint)
	if err != nil {
		return nil, nil, fmt.Errorf("x25519 pubkey: %w", err)
	}
	return priv, pub, nil
}

// ── Signing ──────────────────────────────────────────────────

// SignMessage signs a JSON-serializable payload with an ed25519 seed.
// The payload is canonicalized (sorted keys) before signing.
func SignMessage(seed []byte, payload any) (string, error) {
	priv := ed25519.NewKeyFromSeed(seed)

	canonical, err := canonicalJSON(payload)
	if err != nil {
		return "", fmt.Errorf("canonical json: %w", err)
	}

	sig := ed25519.Sign(priv, canonical)
	return base64.RawURLEncoding.EncodeToString(sig), nil
}

// VerifySignature checks an ed25519 signature against a payload.
func VerifySignature(pubKey ed25519.PublicKey, payload any, signatureB64 string) bool {
	canonical, err := canonicalJSON(payload)
	if err != nil {
		return false
	}

	sig, err := base64.RawURLEncoding.DecodeString(signatureB64)
	if err != nil {
		return false
	}

	return ed25519.Verify(pubKey, canonical, sig)
}

// ── E2E Encryption (ECDHE + AES-256-GCM) ────────────────────

// DeriveSharedKey derives a 32-byte AES key via X25519 ECDHE + HKDF.
// Uses HKDF-SHA256 with salt="elo-e2e-v1" and info="elo-e2e" —
// matches the Python SDK exactly for cross-runtime E2E compatibility.
func DeriveSharedKey(ourPrivate, theirPublic []byte) ([]byte, error) {
	shared, err := curve25519.X25519(ourPrivate, theirPublic)
	if err != nil {
		return nil, fmt.Errorf("x25519 exchange: %w", err)
	}

	hkdf := hkdf.New(sha256.New, shared, []byte("elo-e2e-v1"), []byte("elo-e2e"))
	key := make([]byte, 32)
	if _, err := io.ReadFull(hkdf, key); err != nil {
		return nil, fmt.Errorf("hkdf derive: %w", err)
	}
	return key, nil
}

// EncryptPayload encrypts a JSON payload with AES-256-GCM.
// Returns nonce (12) + ciphertext + tag (16).
func EncryptPayload(key []byte, plaintext any, aad []byte) ([]byte, error) {
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, fmt.Errorf("aes: %w", err)
	}

	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, fmt.Errorf("gcm: %w", err)
	}

	data, err := canonicalJSON(plaintext)
	if err != nil {
		return nil, fmt.Errorf("json: %w", err)
	}

	nonce := make([]byte, gcm.NonceSize())
	if _, err := rand.Read(nonce); err != nil {
		return nil, fmt.Errorf("nonce: %w", err)
	}

	ciphertext := gcm.Seal(nil, nonce, data, aad)
	return append(nonce, ciphertext...), nil
}

// DecryptPayload decrypts an AES-256-GCM payload.
func DecryptPayload(key, encrypted, aad []byte) (map[string]any, error) {
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, fmt.Errorf("aes: %w", err)
	}

	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, fmt.Errorf("gcm: %w", err)
	}

	nonceSize := gcm.NonceSize()
	if len(encrypted) < nonceSize {
		return nil, fmt.Errorf("ciphertext too short")
	}

	nonce := encrypted[:nonceSize]
	ciphertext := encrypted[nonceSize:]

	plaintext, err := gcm.Open(nil, nonce, ciphertext, aad)
	if err != nil {
		return nil, fmt.Errorf("decrypt: %w", err)
	}

	var result map[string]any
	if err := json.Unmarshal(plaintext, &result); err != nil {
		return nil, fmt.Errorf("unmarshal: %w", err)
	}
	return result, nil
}

// ── helpers ──────────────────────────────────────────────────

// canonicalJSON serializes to compact JSON with sorted keys.
func canonicalJSON(v any) ([]byte, error) {
	// For maps, sort keys
	if m, ok := v.(map[string]any); ok {
		return sortedJSON(m), nil
	}
	// For structs, use json.Marshal (field order is fixed by struct tags)
	return json.Marshal(v)
}

func sortedJSON(m map[string]any) []byte {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	sort.Strings(keys)

	var buf []byte
	buf = append(buf, '{')
	for i, k := range keys {
		if i > 0 {
			buf = append(buf, ',')
		}
		keyJSON, _ := json.Marshal(k)
		buf = append(buf, keyJSON...)
		buf = append(buf, ':')

		// Recursively handle nested maps
		if nested, ok := m[k].(map[string]any); ok {
			buf = append(buf, sortedJSON(nested)...)
		} else {
			valJSON, _ := json.Marshal(m[k])
			buf = append(buf, valJSON...)
		}
	}
	buf = append(buf, '}')
	return buf
}
