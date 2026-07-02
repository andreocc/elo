"""Interest-based routing table.

Each node maintains:
- Local caps: what this node provides
- Local interests: what this node is looking for
- Remote caps: per-peer, what capabilities each peer has
- Remote interests: per-peer, what each peer is looking for
- Forwarding table: capability → set of peer addresses that can serve it
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any


class InterestTable:
    """Interest-based routing for P2P capability discovery."""

    def __init__(self) -> None:
        self._local_caps: set[str] = set()
        self._local_interests: set[str] = set()

        # peer_address → {capability, ...}
        self._peer_caps: dict[str, set[str]] = {}
        self._peer_interests: dict[str, set[str]] = {}

        # capability → {peer_address, ...}
        self._forwarding: dict[str, set[str]] = defaultdict(set)

    # ── local ───────────────────────────────────────────────

    def set_local_caps(self, caps: dict[str, list[dict[str, Any]]]) -> None:
        """Register local capabilities from agents, models, and tools."""
        self._local_caps.clear()
        for agent in caps.get("agents", []):
            self._local_caps.add(agent.get("name", ""))
        for model in caps.get("models", []):
            self._local_caps.add(model.get("name", ""))
        for tool in caps.get("tools", []):
            self._local_caps.add(tool.get("name", ""))

    def set_local_interests(self, interests: list[str]) -> None:
        self._local_interests = set(interests)

    def has_local(self, capability: str) -> bool:
        return capability in self._local_caps

    @property
    def local_caps(self) -> set[str]:
        return self._local_caps

    @property
    def local_interests(self) -> set[str]:
        return self._local_interests

    # ── peer ────────────────────────────────────────────────

    def register_peer(self, peer_addr: str, caps: dict[str, list[dict[str, Any]]],
                      interests: list[str]) -> None:
        """Register or update a peer's capabilities and interests."""
        cap_set: set[str] = set()
        for agent in caps.get("agents", []):
            cap_set.add(agent.get("name", ""))
        for model in caps.get("models", []):
            cap_set.add(model.get("name", ""))
        for tool in caps.get("tools", []):
            cap_set.add(tool.get("name", ""))

        self._peer_caps[peer_addr] = cap_set
        self._peer_interests[peer_addr] = set(interests)

        # Update forwarding table
        for cap in cap_set:
            self._forwarding[cap].add(peer_addr)

    def remove_peer(self, peer_addr: str) -> None:
        """Remove a peer and clean forwarding entries."""
        old_caps = self._peer_caps.pop(peer_addr, set())
        for cap in old_caps:
            self._forwarding.get(cap, set()).discard(peer_addr)
        self._peer_interests.pop(peer_addr, None)

    def find_peer_for(self, capability: str) -> str | None:
        """Find a peer that can serve the given capability."""
        peers = self._forwarding.get(capability, set())
        if peers:
            return next(iter(peers))
        return None

    def find_all_peers_for(self, capability: str) -> set[str]:
        """Return all known peers for a capability."""
        return self._forwarding.get(capability, set()).copy()

    def query_peers(self, capability: str, exclude: set[str] | None = None) -> list[str]:
        """Find peers that might know about a capability.

        First: direct matches from forwarding table.
        Second: peers whose interests overlap (they're looking for similar things).
        Third: random peers as a fallback.
        """
        exclude = exclude or set()
        results: list[str] = []

        # Direct matches
        for peer in self._forwarding.get(capability, set()):
            if peer not in exclude:
                results.append(peer)

        # Peers with overlapping interests (might know about this capability)
        if not results:
            for peer_addr, interests in self._peer_interests.items():
                if peer_addr in exclude:
                    continue
                # If the peer is interested in something, it might know
                # about similar capabilities
                if any(capability.startswith(i.split(":")[0])
                       for i in interests):
                    results.append(peer_addr)

        # Fallback: all known peers
        if not results:
            results = [p for p in self._peer_caps if p not in exclude]

        return results

    @property
    def known_peers(self) -> list[str]:
        return list(self._peer_caps.keys())

    def get_peer_caps(self, peer_addr: str) -> dict[str, set[str]]:
        return {
            "caps": self._peer_caps.get(peer_addr, set()),
            "interests": self._peer_interests.get(peer_addr, set()),
        }
