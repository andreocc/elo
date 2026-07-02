package transport

import (
	"fmt"
	"io"
	"log"
	"net"
	"sync"
	"time"
)

// PeerConn represents a single TCP connection to a peer.
type PeerConn struct {
	Addr     string
	conn     net.Conn
	mu       sync.Mutex
	lastRead time.Time
	alive    bool
}

// Send writes a framed message to the peer.
func (p *PeerConn) Send(msg map[string]any) error {
	p.mu.Lock()
	defer p.mu.Unlock()
	if !p.alive {
		return fmt.Errorf("peer disconnected")
	}
	frame, err := EncodeFrame(msg)
	if err != nil {
		return err
	}
	_, err = p.conn.Write(frame)
	return err
}

// Recv reads a framed message from the peer.
func (p *PeerConn) Recv() (map[string]any, error) {
	msg, err := ReadFrame(p.conn)
	if err != nil {
		p.alive = false
		return nil, err
	}
	p.lastRead = time.Now()
	return msg, nil
}

// Close closes the connection.
func (p *PeerConn) Close() {
	p.alive = false
	p.conn.Close()
}

// Idle returns the time since the last read.
func (p *PeerConn) Idle() time.Duration {
	return time.Since(p.lastRead)
}

// MessageHandler is the callback for incoming messages: (peerAddr, message).
type MessageHandler func(peerAddr string, msg map[string]any)

// TCPManager manages all TCP peer connections.
type TCPManager struct {
	nodeID   string
	host     string
	port     int
	listener net.Listener
	peers    map[string]*PeerConn
	mu       sync.RWMutex
	handler  MessageHandler
	shutdown chan struct{}
}

// NewTCPManager creates a new TCP connection manager.
func NewTCPManager(nodeID string, host string, port int) *TCPManager {
	return &TCPManager{
		nodeID:   nodeID,
		host:     host,
		port:     port,
		peers:    make(map[string]*PeerConn),
		shutdown: make(chan struct{}),
	}
}

// Start starts the TCP server.
func (m *TCPManager) Start() (int, error) {
	addr := fmt.Sprintf("%s:%d", m.host, m.port)
	l, err := net.Listen("tcp", addr)
	if err != nil {
		return 0, fmt.Errorf("listen: %w", err)
	}
	m.listener = l
	m.port = l.Addr().(*net.TCPAddr).Port

	go m.acceptLoop()
	log.Printf("[tcp] listening on %s:%d", m.host, m.port)
	return m.port, nil
}

// Stop shuts down the server and closes all peer connections.
func (m *TCPManager) Stop() {
	close(m.shutdown)
	if m.listener != nil {
		m.listener.Close()
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	for _, p := range m.peers {
		p.Close()
	}
	m.peers = make(map[string]*PeerConn)
}

// OnMessage registers the message handler.
func (m *TCPManager) OnMessage(handler MessageHandler) {
	m.handler = handler
}

// Port returns the listening port.
func (m *TCPManager) Port() int { return m.port }

// PeerCount returns the number of connected peers.
func (m *TCPManager) PeerCount() int {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return len(m.peers)
}

// PeerAddresses returns all connected peer addresses.
func (m *TCPManager) PeerAddresses() []string {
	m.mu.RLock()
	defer m.mu.RUnlock()
	addrs := make([]string, 0, len(m.peers))
	for a := range m.peers {
		addrs = append(addrs, a)
	}
	return addrs
}

// HasPeer checks if a peer is connected.
func (m *TCPManager) HasPeer(addr string) bool {
	m.mu.RLock()
	defer m.mu.RUnlock()
	_, ok := m.peers[addr]
	return ok
}

// SendTo sends a message to a specific peer.
func (m *TCPManager) SendTo(peerAddr string, msg map[string]any) error {
	m.mu.RLock()
	p, ok := m.peers[peerAddr]
	m.mu.RUnlock()
	if !ok {
		return fmt.Errorf("peer not found: %s", peerAddr)
	}
	return p.Send(msg)
}

// Broadcast sends a message to all peers.
func (m *TCPManager) Broadcast(msg map[string]any, exclude map[string]bool) error {
	m.mu.RLock()
	defer m.mu.RUnlock()
	for addr, p := range m.peers {
		if exclude != nil && exclude[addr] {
			continue
		}
		if err := p.Send(msg); err != nil {
			log.Printf("[tcp] broadcast failed to %s: %v", addr, err)
		}
	}
	return nil
}

// ConnectToPeer connects to a remote peer.
func (m *TCPManager) ConnectToPeer(addr string, hello map[string]any) (string, error) {
	m.mu.RLock()
	if _, exists := m.peers[addr]; exists {
		m.mu.RUnlock()
		return addr, nil
	}
	m.mu.RUnlock()

	conn, err := net.DialTimeout("tcp", addr, 10*time.Second)
	if err != nil {
		return "", fmt.Errorf("dial %s: %w", addr, err)
	}

	peer := &PeerConn{
		Addr:     addr,
		conn:     conn,
		alive:    true,
		lastRead: time.Now(),
	}

	// Send HELLO
	if hello != nil {
		if err := peer.Send(hello); err != nil {
			conn.Close()
			return "", err
		}
	}

	// Read HELLO_ACK
	conn.SetReadDeadline(time.Now().Add(5 * time.Second))
	ack, err := peer.Recv()
	conn.SetReadDeadline(time.Time{})
	if err != nil || ack["type"] != MsgHelloAck {
		conn.Close()
		return "", fmt.Errorf("no hello_ack from %s", addr)
	}

	m.mu.Lock()
	m.peers[addr] = peer
	m.mu.Unlock()

	// Start read loop
	go m.readLoop(addr, peer)

	return addr, nil
}

func (m *TCPManager) acceptLoop() {
	for {
		select {
		case <-m.shutdown:
			return
		default:
		}
		conn, err := m.listener.Accept()
		if err != nil {
			select {
			case <-m.shutdown:
				return
			default:
				continue
			}
		}
		go m.handleConn(conn)
	}
}

func (m *TCPManager) handleConn(conn net.Conn) {
	addr := conn.RemoteAddr().String()
	peer := &PeerConn{
		Addr:     addr,
		conn:     conn,
		alive:    true,
		lastRead: time.Now(),
	}

	// Expect HELLO first
	conn.SetReadDeadline(time.Now().Add(10 * time.Second))
	hello, err := peer.Recv()
	conn.SetReadDeadline(time.Time{})
	if err != nil || hello["type"] != MsgHello {
		conn.Close()
		return
	}

	m.mu.Lock()
	m.peers[addr] = peer
	m.mu.Unlock()

	if m.handler != nil {
		m.handler(addr, hello)
	}

	m.readLoop(addr, peer)
}

func (m *TCPManager) readLoop(addr string, peer *PeerConn) {
	for {
		peer.conn.SetReadDeadline(time.Now().Add(90 * time.Second))
		msg, err := peer.Recv()
		if err != nil {
			if err == io.EOF || !peer.alive {
				break
			}
			continue
		}
		if m.handler != nil {
			m.handler(addr, msg)
		}
	}

	m.mu.Lock()
	delete(m.peers, addr)
	m.mu.Unlock()
	peer.Close()
	if m.handler != nil {
		m.handler(addr, ByeMsg())
	}
}
