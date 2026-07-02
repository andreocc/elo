"""Elo P2P transport layer — zero-infra mesh networking.

Modules:
- tcp: TCP connection manager (server + peer connections)
- protocol: Wire protocol — framed JSON over TCP
- routing: Interest-based routing table
- tracker: Local capability registry (public/private)
"""

from elo.transport.tcp import TCPManager, PeerConnection
from elo.transport.protocol import (
    encode_frame, read_frame, write_frame,
    hello_msg, hello_ack_msg,
    query_msg, query_resp_msg,
    interest_update_msg,
    task_msg, result_msg,
    heartbeat_msg, bye_msg,
    MessageType, FrameError,
)
from elo.transport.routing import InterestTable
from elo.transport.tracker import LocalTracker

__all__ = [
    "TCPManager", "PeerConnection",
    "encode_frame", "read_frame", "write_frame",
    "hello_msg", "hello_ack_msg",
    "query_msg", "query_resp_msg",
    "interest_update_msg",
    "task_msg", "result_msg",
    "heartbeat_msg", "bye_msg",
    "MessageType", "FrameError",
    "InterestTable",
    "LocalTracker",
]
