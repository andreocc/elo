"""Local tracker — each node publishes its own agent/tool registry."""

from __future__ import annotations

from typing import Any


class LocalTracker:
    """A node's local registry of agents, models, and tools.

    Visibility modes:
    - "public": any connected peer can query capabilities
    - "private": only peers in the allowlist can query
    """

    def __init__(self, visibility: str = "public"):
        self._visibility = visibility
        self._caps: dict[str, list[dict[str, str]]] = {
            "agents": [],
            "models": [],
            "tools": [],
        }
        self._allowlist: set[str] = set()  # node_ids (for private mode)
        self._interests: list[str] = []

    # ── visibility ───────────────────────────────────────────

    @property
    def visibility(self) -> str:
        return self._visibility

    def set_visibility(self, mode: str) -> None:
        if mode not in ("public", "private"):
            raise ValueError(f"Invalid visibility: {mode}")
        self._visibility = mode

    def allow_peer(self, node_id: str) -> None:
        self._allowlist.add(node_id)

    def revoke_peer(self, node_id: str) -> None:
        self._allowlist.discard(node_id)

    def is_allowed(self, node_id: str) -> bool:
        if self._visibility == "public":
            return True
        return node_id in self._allowlist

    # ── caps ─────────────────────────────────────────────────

    def register(self, *, agents: list[dict[str, str]] | None = None,
                 models: list[dict[str, str]] | None = None,
                 tools: list[dict[str, str]] | None = None) -> None:
        if agents:
            self._caps["agents"] = agents
        if models:
            self._caps["models"] = models
        if tools:
            self._caps["tools"] = tools

    def set_interests(self, interests: list[str]) -> None:
        self._interests = interests

    def get_caps_for_peer(self, node_id: str) -> dict[str, list[dict[str, str]]]:
        """Return capabilities visible to the given peer."""
        if self.is_allowed(node_id):
            return self._caps
        return {"agents": [], "models": [], "tools": []}

    def get_public_caps(self) -> dict[str, list[dict[str, str]]]:
        """Return capabilities for public advertisement (HELLO)."""
        if self._visibility == "public":
            return self._caps
        return {"agents": [], "models": [], "tools": []}

    @property
    def caps(self) -> dict[str, list[dict[str, str]]]:
        return self._caps

    @property
    def interests(self) -> list[str]:
        return self._interests

    def has_capability(self, name: str) -> bool:
        """Check if this node has a specific capability."""
        for category in ("agents", "models", "tools"):
            for item in self._caps[category]:
                if item.get("name") == name:
                    return True
        return False

    def match(self, capability: str) -> dict[str, Any] | None:
        """Match a capability by name. Returns the matched item or None."""
        for category in ("agents", "models", "tools"):
            for item in self._caps[category]:
                if item.get("name") == capability:
                    return {"category": category, **item}
        return None
