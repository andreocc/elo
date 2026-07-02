"""Wire protocol — framed JSON messages over TCP.

Frame format: [4-byte big-endian length][JSON payload]
"""

from __future__ import annotations

import asyncio
import json
import struct
import time
from typing import Any

# ── Frame constants ────────────────────────────────────────

FRAME_HEADER_SIZE = 4  # uint32 big-endian
MAX_PAYLOAD_SIZE = 1024 * 1024  # 1 MB


class FrameError(Exception):
    """Invalid frame received."""


# ── Message types ──────────────────────────────────────────

class MessageType:
    HELLO = "hello"
    HELLO_ACK = "hello_ack"
    QUERY = "query"
    QUERY_RESP = "query_resp"
    INTEREST_UPDATE = "interest_update"
    TASK = "task"
    RESULT = "result"
    EVENT = "event"
    HEARTBEAT = "heartbeat"
    BYE = "bye"
    # DHT messages (v0.3+)
    DHT_PING = "dht_ping"
    DHT_PONG = "dht_pong"
    DHT_FIND_NODE = "dht_find_node"
    DHT_FIND_NODE_RESP = "dht_find_node_resp"
    DHT_FIND_VALUE = "dht_find_value"
    DHT_FIND_VALUE_RESP = "dht_find_value_resp"
    DHT_STORE = "dht_store"
    DHT_STORE_RESP = "dht_store_resp"


# ── Framing ────────────────────────────────────────────────


def encode_frame(payload: dict[str, Any]) -> bytes:
    """Encodes a JSON dict into a framed message."""
    data = json.dumps(payload, ensure_ascii=False).encode()
    if len(data) > MAX_PAYLOAD_SIZE:
        raise FrameError(f"Payload too large: {len(data)} bytes (max {MAX_PAYLOAD_SIZE})")
    header = struct.pack("!I", len(data))
    return header + data


async def read_frame(reader: asyncio.StreamReader) -> dict[str, Any]:
    """Reads one frame from a StreamReader. Returns the decoded JSON dict."""
    header = await reader.readexactly(FRAME_HEADER_SIZE)
    length = struct.unpack("!I", header)[0]
    if length > MAX_PAYLOAD_SIZE:
        raise FrameError(f"Invalid payload length: {length} (max {MAX_PAYLOAD_SIZE})")
    data = await reader.readexactly(length)
    return json.loads(data.decode())


async def write_frame(writer: asyncio.StreamWriter, payload: dict[str, Any]) -> None:
    """Writes one framed JSON message to a StreamWriter."""
    writer.write(encode_frame(payload))
    await writer.drain()


# ── Message builders ───────────────────────────────────────


def hello_msg(node_id: str, caps: dict, interests: list[str],
              tracker: str = "public", version: str = "0.2.0") -> dict:
    return {
        "type": MessageType.HELLO,
        "node_id": node_id,
        "caps": caps,
        "interests": interests,
        "tracker": tracker,
        "version": version,
    }


def hello_ack_msg(node_id: str, caps: dict, interests: list[str],
                  tracker: str = "public",
                  known_peers: list[dict] | None = None) -> dict:
    msg: dict[str, Any] = {
        "type": MessageType.HELLO_ACK,
        "node_id": node_id,
        "caps": caps,
        "interests": interests,
        "tracker": tracker,
    }
    if known_peers is not None:
        msg["known_peers"] = known_peers
    return msg


def query_msg(capability: str, query_id: str, ttl: int = 5, origin: str = "") -> dict:
    msg: dict[str, Any] = {
        "type": MessageType.QUERY,
        "capability": capability,
        "id": query_id,
        "ttl": ttl,
    }
    if origin:
        msg["origin"] = origin
    return msg


def query_resp_msg(query_id: str, nodes: list[dict]) -> dict:
    return {
        "type": MessageType.QUERY_RESP,
        "id": query_id,
        "nodes": nodes,
    }


def interest_update_msg(interests: list[str]) -> dict:
    return {
        "type": MessageType.INTEREST_UPDATE,
        "interests": interests,
    }


def task_msg(task_id: str, target: str, caller: str, capability: str,
             payload: dict, signature: str = "") -> dict:
    return {
        "type": MessageType.TASK,
        "id": task_id,
        "target": target,
        "caller": caller,
        "capability": capability,
        "payload": payload,
        "signature": signature,
        "protocol": "elo.v1",
        "timestamp": int(time.time()),
        "ttl_s": 60,
    }


def result_msg(task_id: str, status: str, payload: dict | None = None,
               error: dict | None = None, signature: str = "") -> dict:
    msg = {
        "type": MessageType.RESULT,
        "id": task_id,
        "status": status,
        "protocol": "elo.v1",
    }
    if payload is not None:
        msg["payload"] = payload
    if error is not None:
        msg["error"] = error
    if signature:
        msg["signature"] = signature
    return msg


def heartbeat_msg(node_id: str) -> dict:
    return {
        "type": MessageType.HEARTBEAT,
        "node_id": node_id,
        "ts": int(time.time()),
    }


def bye_msg() -> dict:
    return {"type": MessageType.BYE}
