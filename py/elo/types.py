"""Tipos do protocolo Elo v1."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any
import uuid


@dataclass
class AgentCap:
    name: str
    description: str = ""
    model: str = ""


@dataclass
class ModelCap:
    name: str
    provider: str = ""
    context: int = 0


@dataclass
class ToolCap:
    name: str
    description: str = ""
    version: str = ""


@dataclass
class Capabilities:
    agents: list[AgentCap] = field(default_factory=list)
    models: list[ModelCap] = field(default_factory=list)
    tools: list[ToolCap] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class NodeInfo:
    name: str
    version: str = "0.1.0"
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = "online"
    public_key: str = ""
    nats_url: str = ""
    labels: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Task:
    target: str
    caller: str
    capability: str
    payload: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    protocol: str = "elo.v1"
    type: str = "task"
    timestamp: int = field(default_factory=lambda: int(datetime.now(timezone.utc).timestamp()))
    ttl_s: int = 60
    signature: str = ""           # Assinatura ed25519 do caller

    def to_dict(self) -> dict:
        d = asdict(self)
        d["type"] = "task"
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        return cls(
            id=data.get("id", ""),
            protocol=data.get("protocol", "elo.v1"),
            timestamp=data.get("timestamp", 0),
            target=data.get("target", ""),
            caller=data.get("caller", ""),
            capability=data.get("capability", ""),
            payload=data.get("payload", {}),
            ttl_s=data.get("ttl_s", 60),
            signature=data.get("signature", ""),
        )


@dataclass
class Result:
    id: str
    status: str  # "success" | "error" | "timeout"
    payload: dict[str, Any] = field(default_factory=dict)
    error: dict[str, str] | None = None
    protocol: str = "elo.v1"
    type: str = "result"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["type"] = "result"
        if self.error is None:
            del d["error"]
        return d

    @classmethod
    def success(cls, task_id: str, payload: dict[str, Any]) -> "Result":
        return cls(id=task_id, status="success", payload=payload)

    @classmethod
    def make_error(cls, task_id: str, code: str, message: str) -> "Result":
        return cls(id=task_id, status="error", error={"code": code, "message": message})


@dataclass
class Event:
    event_type: str  # "task.completed" | "node.online" | "node.offline" | "capability.changed"
    data: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    protocol: str = "elo.v1"
    type: str = "event"
    timestamp: int = field(default_factory=lambda: int(datetime.now(timezone.utc).timestamp()))

    def to_dict(self) -> dict:
        d = asdict(self)
        d["type"] = "event"
        return d
