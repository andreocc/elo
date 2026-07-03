import asyncio
import socket
import struct
import json
import logging

logger = logging.getLogger("elo.transport.discovery")

MCAST_GRP = "239.255.43.21"
MCAST_PORT = 7879


class MulticastProtocol(asyncio.DatagramProtocol):
    def __init__(self, callback):
        self.callback = callback

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        try:
            msg = json.loads(data.decode("utf-8"))
            self.callback(msg, addr)
        except Exception:
            pass


def create_multicast_socket(port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except AttributeError:
        pass
    sock.bind(("", port))

    mreq = struct.pack("4s4s", socket.inet_aton(MCAST_GRP), socket.inet_aton("0.0.0.0"))
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
    return sock


class DiscoveryManager:
    def __init__(self, node_id: str, port: int, on_peer_discovered):
        self.node_id = node_id
        self.port = port
        self.on_peer_discovered = on_peer_discovered
        self._transport = None
        self._protocol = None
        self._announce_task = None
        self._shutdown = asyncio.Event()

    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        try:
            sock = create_multicast_socket(MCAST_PORT)
            self._transport, self._protocol = await loop.create_datagram_endpoint(
                lambda: MulticastProtocol(self._handle_multicast),
                sock=sock
            )
            self._announce_task = asyncio.create_task(self._announce_loop())
            logger.info("[discovery] started UDP multicast discovery on port %d", MCAST_PORT)
        except Exception as e:
            logger.warning("[discovery] failed to start UDP multicast: %s", e)

    def _handle_multicast(self, msg: dict, addr: tuple[str, int]) -> None:
        if not isinstance(msg, dict):
            return
        mtype = msg.get("type")
        node_id = msg.get("node_id")
        port = msg.get("port")

        if mtype == "announce" and node_id and port:
            if node_id[:12] == self.node_id[:12]:
                return
            peer_ip = addr[0]
            peer_addr = f"{peer_ip}:{port}"
            asyncio.create_task(self.on_peer_discovered(node_id, peer_addr))

    async def announce(self) -> None:
        """Send a single multicast announcement."""
        msg = {
            "type": "announce",
            "node_id": self.node_id,
            "port": self.port
        }
        data = json.dumps(msg).encode("utf-8")
        try:
            if self._transport:
                self._transport.sendto(data, (MCAST_GRP, MCAST_PORT))
            else:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
                try:
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(None, sock.sendto, data, (MCAST_GRP, MCAST_PORT))
                finally:
                    sock.close()
        except Exception as e:
            logger.debug("[discovery] announce failed: %s", e)

    async def _announce_loop(self) -> None:
        while not self._shutdown.is_set():
            await self.announce()
            try:
                await asyncio.wait_for(self._shutdown.wait(), timeout=10.0)
            except asyncio.TimeoutError:
                pass

    async def stop(self) -> None:
        self._shutdown.set()
        if self._announce_task:
            self._announce_task.cancel()
        if self._transport:
            self._transport.close()
