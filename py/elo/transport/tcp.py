"""TCP connection manager — persistent peer connections with framing."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Awaitable
from typing import Any

from elo.transport.protocol import (
    encode_frame,
    read_frame,
    write_frame,
    bye_msg,
    heartbeat_msg,
    FrameError,
    MessageType,
)

logger = logging.getLogger("elo.transport.tcp")

# Message handler signature: (peer_addr: str, message: dict) → None
MessageHandler = Callable[[str, dict[str, Any]], Awaitable[None]]


class PeerConnection:
    """A single TCP connection to a peer."""

    def __init__(self, addr: str, reader: asyncio.StreamReader,
                 writer: asyncio.StreamWriter):
        self.addr = addr
        self._reader = reader
        self._writer = writer
        self._alive = True
        self._last_read = time.monotonic()

    async def send(self, message: dict[str, Any]) -> None:
        """Send a framed message to the peer."""
        if not self._alive:
            raise ConnectionError("Peer disconnected")
        try:
            await write_frame(self._writer, message)
        except Exception:
            self._alive = False
            raise

    async def recv(self) -> dict[str, Any] | None:
        """Receive one framed message from the peer. Returns None on EOF."""
        try:
            msg = await read_frame(self._reader)
            self._last_read = time.monotonic()
            return msg
        except (FrameError, asyncio.IncompleteReadError, ConnectionError):
            self._alive = False
            return None

    def close(self) -> None:
        """Close the connection."""
        self._alive = False
        try:
            self._writer.close()
        except Exception:
            pass

    @property
    def alive(self) -> bool:
        return self._alive

    @property
    def idle_seconds(self) -> float:
        return time.monotonic() - self._last_read


class TCPManager:
    """Manages all TCP peer connections: server + client connections."""

    # Timeout configuration
    CONNECT_TIMEOUT = 10  # seconds
    HEARTBEAT_INTERVAL = 30  # seconds
    HEARTBEAT_IDLE_TIMEOUT = 90  # 3 missed heartbeats

    def __init__(self, node_id: str, host: str = "0.0.0.0", port: int = 7878):
        self._node_id = node_id
        self._host = host
        self._port = port
        self._server: asyncio.Server | None = None
        self._peers: dict[str, PeerConnection] = {}
        self._handler: MessageHandler | None = None
        self._shutdown = asyncio.Event()
        self._heartbeat_task: asyncio.Task | None = None
        self._listen_task: asyncio.Task | None = None

    # ── lifecycle ────────────────────────────────────────────

    async def start(self) -> int:
        """Start the TCP server. Returns the actual port."""
        self._server = await asyncio.start_server(
            self._handle_incoming,
            host=self._host,
            port=self._port,
        )
        # Get the actual port (useful if port=0 for random assignment)
        if self._port == 0 and self._server.sockets:
            self._port = self._server.sockets[0].getsockname()[1]

        logger.info("[tcp] listening on %s:%d", self._host, self._port)
        return self._port

    async def stop(self) -> None:
        """Stop the server and close all peer connections."""
        self._shutdown.set()

        if self._heartbeat_task:
            self._heartbeat_task.cancel()

        # Send BYE to all peers
        for addr, peer in list(self._peers.items()):
            try:
                await peer.send(bye_msg())
            except Exception:
                pass
            peer.close()

        self._peers.clear()

        if self._server:
            self._server.close()
            await self._server.wait_closed()

        logger.info("[tcp] stopped")

    # ── handlers ─────────────────────────────────────────────

    def on_message(self, handler: MessageHandler) -> None:
        """Register a message handler."""
        self._handler = handler

    async def _handle_incoming(self, reader: asyncio.StreamReader,
                               writer: asyncio.StreamWriter) -> None:
        """Handle a new incoming TCP connection."""
        peername = writer.get_extra_info("peername")
        addr = f"{peername[0]}:{peername[1]}" if peername else "unknown"
        logger.debug("[tcp] incoming from %s", addr)

        peer = PeerConnection(addr, reader, writer)

        try:
            # Read HELLO as first message
            hello = await peer.recv()
            if hello is None or hello.get("type") != MessageType.HELLO:
                logger.warning("[tcp] no hello from %s", addr)
                peer.close()
                return

            remote_id = hello.get("node_id", "")
            addr = f"{remote_id[:12]}@{addr}"
            peer.addr = addr

            self._peers[addr] = peer
            logger.info("[tcp] peer connected: %s", addr)

            # Notify handler about the peer + its HELLO
            if self._handler:
                await self._handler(addr, hello)

        except Exception:
            logger.debug("[tcp] connection error from %s", addr, exc_info=True)
            peer.close()
            return

        # Start read loop (shared by inbound and outbound)
        await self._read_loop(addr, peer)

    # ── read loop (shared by inbound + outbound) ───────────

    async def _read_loop(self, addr: str, peer: PeerConnection) -> None:
        """Continuously read messages from a peer until disconnect."""
        try:
            while not self._shutdown.is_set():
                msg = await peer.recv()
                if msg is None:
                    break
                if self._handler:
                    await self._handler(addr, msg)
        except Exception:
            logger.debug("[tcp] read error from %s", addr, exc_info=True)
        finally:
            peer.close()
            self._peers.pop(addr, None)
            if self._handler:
                try:
                    await self._handler(addr, {"type": MessageType.BYE, "node_id": ""})
                except Exception:
                    pass
            logger.info("[tcp] peer disconnected: %s", addr)

    # ── outbound connections ─────────────────────────────────

    async def connect_to_peer(self, addr: str, node_id: str = "unknown",
                               hello_payload: dict | None = None) -> str | None:
        """Connect to a remote peer. Returns the assigned peer address on success."""
        if ":" not in addr:
            logger.warning("[tcp] invalid address: %s", addr)
            return None

        # Normalize: if no port, use default
        host, _, port_str = addr.partition(":")
        port = int(port_str) if port_str else self._port
        canonical = f"{host}:{port}"

        if canonical in self._peers:
            return canonical

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=self.CONNECT_TIMEOUT,
            )
        except Exception as e:
            logger.debug("[tcp] connect to %s failed: %s", canonical, e)
            return None

        peer = PeerConnection(canonical, reader, writer)

        # Send HELLO
        if hello_payload:
            await peer.send(hello_payload)

        # Wait for HELLO_ACK
        try:
            ack = await asyncio.wait_for(peer.recv(), timeout=5)
        except asyncio.TimeoutError:
            peer.close()
            return None

        if ack is None or ack.get("type") != MessageType.HELLO_ACK:
            peer.close()
            return None

        remote_id = ack.get("node_id", "")
        display_addr = f"{remote_id[:12]}@{canonical}"
        peer.addr = display_addr

        self._peers[display_addr] = peer

        # Notify handler with HELLO_ACK
        if self._handler:
            await self._handler(display_addr, ack)

        logger.info("[tcp] connected to %s", display_addr)

        # Start read loop in background
        asyncio.create_task(self._read_loop(display_addr, peer))

        return display_addr

    async def send_to(self, peer_addr: str, message: dict[str, Any]) -> None:
        """Send a message to a specific peer."""
        peer = self._peers.get(peer_addr)
        if peer is None:
            raise ConnectionError(f"Peer not connected: {peer_addr}")
        await peer.send(message)

    # ── broadcast ────────────────────────────────────────────

    async def broadcast(self, message: dict[str, Any],
                        exclude: set[str] | None = None) -> None:
        """Send a message to all connected peers."""
        exclude = exclude or set()
        for addr, peer in list(self._peers.items()):
            if addr in exclude:
                continue
            try:
                await peer.send(message)
            except Exception:
                logger.debug("[tcp] broadcast failed to %s", addr)

    # ── heartbeat ────────────────────────────────────────────

    async def start_heartbeat(self) -> None:
        """Periodically send heartbeats and purge dead peers."""
        while not self._shutdown.is_set():
            try:
                await asyncio.wait_for(
                    self._shutdown.wait(),
                    timeout=self.HEARTBEAT_INTERVAL,
                )
                break
            except asyncio.TimeoutError:
                pass

            hb = heartbeat_msg(self._node_id)
            dead = []

            for addr, peer in list(self._peers.items()):
                try:
                    await peer.send(hb)
                except Exception:
                    dead.append(addr)

                # Check idle timeout
                if peer.idle_seconds > self.HEARTBEAT_IDLE_TIMEOUT:
                    dead.append(addr)

            for addr in set(dead):
                peer = self._peers.pop(addr, None)
                if peer:
                    peer.close()
                    if self._handler:
                        await self._handler(addr,
                                          {"type": MessageType.BYE, "node_id": ""})
                    logger.info("[tcp] peer timed out: %s", addr)

    # ── accessors ────────────────────────────────────────────

    @property
    def peer_count(self) -> int:
        return len(self._peers)

    @property
    def peer_addresses(self) -> list[str]:
        return list(self._peers.keys())

    @property
    def port(self) -> int:
        return self._port
