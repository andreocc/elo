"""Testes unitários do SDK Python P2P v0.4."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from elo import Node, Task, Result, Capabilities
from elo.types import AgentCap, ModelCap, ToolCap
from elo.transport import (
    InterestTable,
    LocalTracker,
    MessageType,
    hello_msg,
    query_msg,
    query_resp_msg,
    task_msg as p2p_task_msg,
    result_msg,
    encode_frame,
    FrameError,
)


# ── TestTypes ───────────────────────────────────────────────

class TestTypes:
    def test_agent_cap_defaults(self):
        cap = AgentCap(name="test-agent")
        assert cap.name == "test-agent"

    def test_task_from_dict(self):
        data = {
            "id": "abc-123", "protocol": "elo.v1", "timestamp": 1700000000,
            "target": "target-node", "caller": "caller-node",
            "capability": "analyst", "payload": {"key": "value"}, "ttl_s": 30,
        }
        task = Task.from_dict(data)
        assert task.id == "abc-123"
        assert task.capability == "analyst"

    def test_result_success(self):
        r = Result.success("task-1", {"output": "ok"})
        assert r.status == "success"

    def test_result_error(self):
        r = Result.make_error("task-1", "TIMEOUT", "No response")
        assert r.status == "error"
        assert r.error["code"] == "TIMEOUT"


# ── TestTransportProtocol ──────────────────────────────────

class TestTransportProtocol:
    def test_encode_decode_frame(self):
        frame = encode_frame({"type": "hello", "node_id": "test123"})
        assert len(frame) == 4 + len(json.dumps({"type": "hello", "node_id": "test123"}))

    def test_encode_too_large(self):
        with pytest.raises(FrameError):
            encode_frame({"data": "x" * (1024 * 1024 + 1)})

    def test_hello_msg(self):
        msg = hello_msg("node123", {"agents": [{"name": "test"}]}, ["analyst"], "public")
        assert msg["type"] == MessageType.HELLO
        assert msg["node_id"] == "node123"

    def test_query_msg(self):
        msg = query_msg("analyst", "q1", ttl=3)
        assert msg["type"] == MessageType.QUERY
        assert msg["capability"] == "analyst"

    def test_task_msg(self):
        msg = p2p_task_msg("t1", "target", "caller", "echo", {"msg": "hi"})
        assert msg["type"] == MessageType.TASK
        assert msg["capability"] == "echo"

    def test_result_msg(self):
        msg = result_msg("t1", "success", payload={"result": "ok"})
        assert msg["type"] == MessageType.RESULT
        assert msg["payload"] == {"result": "ok"}


# ── TestInterestTable ──────────────────────────────────────

class TestInterestTable:
    def test_empty_table(self):
        t = InterestTable()
        assert t.find_peer_for("analyst") is None

    def test_register_peer(self):
        t = InterestTable()
        t.register_peer("peer1:7878", {"agents": [{"name": "analyst"}], "tools": [], "models": []}, ["writer"])
        assert t.find_peer_for("analyst") == "peer1:7878"

    def test_remove_peer(self):
        t = InterestTable()
        t.register_peer("peer1:7878", {"agents": [{"name": "analyst"}], "tools": [], "models": []}, [])
        t.remove_peer("peer1:7878")
        assert t.find_peer_for("analyst") is None

    def test_local_caps(self):
        t = InterestTable()
        t.set_local_caps({"agents": [{"name": "echo"}], "tools": [], "models": []})
        assert t.has_local("echo")


# ── TestLocalTracker ───────────────────────────────────────

class TestLocalTracker:
    def test_public_tracker(self):
        tr = LocalTracker("public")
        tr.register(agents=[{"name": "echo"}])
        assert len(tr.get_caps_for_peer("anyone")["agents"]) == 1

    def test_private_tracker(self):
        tr = LocalTracker("private")
        tr.register(agents=[{"name": "secret-agent"}])
        assert len(tr.get_caps_for_peer("stranger")["agents"]) == 0
        tr.allow_peer("friend")
        assert len(tr.get_caps_for_peer("friend")["agents"]) == 1

    def test_has_capability(self):
        tr = LocalTracker("public")
        tr.register(agents=[{"name": "analyst", "model": "gpt-4"}], tools=[{"name": "web-search"}])
        assert tr.has_capability("analyst")
        assert tr.has_capability("web-search")
        assert not tr.has_capability("writer")


# ── TestNodeConstruction ────────────────────────────────────

class TestNodeConstruction:
    def test_default_values(self):
        node = Node("test-node")
        assert node._name == "test-node"
        assert node._port == 7878
        assert node._version == "0.4.9"
        assert node.connected is False
        assert node.node_id is not None
        assert len(node.node_id) > 20

    def test_custom_values(self):
        node = Node("prod-node", port=9000, peers=["10.0.0.1:7878"],
                    tracker="private", version="1.0.0", heartbeat_interval_s=15,
                    labels={"region": "br"})
        assert node._port == 9000
        assert node.tracker_visibility == "private"

    @pytest.mark.asyncio
    async def test_send_task_to_offline_target_returns_error(self):
        """send_task with offline target_node must return error, not route to tracker."""
        node = Node("test-a", port=0)
        await node.connect()
        await node.register(agents=["echo"])

        # Target node_id that won't match any connected peer address
        result = await node.send_task("nonexistent-node-id-42", "echo", {"msg": "hello"})

        assert result.status == "error"
        await node.disconnect()


# ── TestNodeLifecycle ──────────────────────────────────────

class TestNodeLifecycle:
    @pytest.mark.asyncio
    async def test_connect_starts_server(self):
        node = Node("test", port=0)
        await node.connect()
        assert node.connected
        assert node.port > 0
        await node.disconnect()

    @pytest.mark.asyncio
    async def test_double_connect_idempotent(self):
        node = Node("test", port=0)
        await node.connect()
        port = node.port
        await node.connect()
        assert node.port == port
        await node.disconnect()

    @pytest.mark.asyncio
    async def test_register_agents(self):
        node = Node("test", port=0)
        await node.connect()
        await node.register(agents=["analyst", "writer"])
        assert node._tracker.has_capability("analyst")
        assert node._routing.has_local("analyst")
        await node.disconnect()

    @pytest.mark.asyncio
    async def test_register_tools(self):
        node = Node("test", port=0)
        await node.connect()
        await node.register(models=["gpt-4o"], tools=["web-search"])
        assert node._tracker.has_capability("web-search")
        await node.disconnect()


# ── TestErrorHandling ───────────────────────────────────────

class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_send_task_not_connected(self):
        node = Node("test")
        with pytest.raises(RuntimeError, match="not connected"):
            await node.send_task("target", "cap", {})

    @pytest.mark.asyncio
    async def test_run_not_connected(self):
        node = Node("test")
        with pytest.raises(RuntimeError, match="not connected"):
            await node.run()


# ── TestResultMatching ─────────────────────────────────────

class TestResultMatching:
    """Testa que _pending_results dict é reentrante (não tem race condition)."""

    @pytest.mark.asyncio
    async def test_concurrent_results_dont_conflict(self):
        """Duas tasks simultâneas devem cada uma receber seu próprio resultado."""
        node = Node("test", port=0)
        await node.connect()

        # Simula dois resultados chegando para duas tasks diferentes
        f1 = asyncio.get_event_loop().create_future()
        f2 = asyncio.get_event_loop().create_future()
        node._pending_results["task-1"] = f1
        node._pending_results["task-2"] = f2

        # _on_result dispatch
        await node._on_result("peer1", {"id": "task-1", "status": "success", "payload": {"r": 1}})
        await node._on_result("peer1", {"id": "task-2", "status": "success", "payload": {"r": 2}})

        r1 = await f1
        r2 = await f2
        assert r1.payload == {"r": 1}
        assert r2.payload == {"r": 2}
        # Cleanup (normally done by _wait_for_result)
        node._pending_results.clear()

        await node.disconnect()


# ── TestNodeQueryResponse ────────────────────────────────

class TestNodeQueryResponse:
    """Verifica que _on_query retorna node_id nos nodes."""

    @pytest.mark.asyncio
    async def test_on_query_returns_node_id(self):
        """_on_query must include node_id in discover_peers_network() response."""
        node = Node("test-query", port=0)
        await node.connect()
        await node.register(agents=["echo"])

        # Register a peer with node_id embedded in address: node_id@host:port
        node._routing.register_peer(
            "abc123@10.0.0.1:7878",
            {"agents": [{"name": "echo"}], "tools": [], "models": []},
            ["echo"],
        )

        # Spy on _tcp.send_to to capture the query response
        sent_msgs = []
        original_send = node._tcp.send_to
        async def spy_send(addr, msg):
            sent_msgs.append(msg)
        node._tcp.send_to = spy_send

        try:
            await node._on_query("10.0.0.2:7879", {"capability": "echo", "id": "q1", "ttl": 3})
        finally:
            node._tcp.send_to = original_send

        assert len(sent_msgs) > 0, "Expected at least one message sent back"
        response = sent_msgs[0]
        nodes = response.get("nodes", [])
        assert len(nodes) > 0, "Expected at least one node in response"

        # Verify the manually registered peer includes node_id
        peer = None
        for n in nodes:
            if n.get("addr") == "abc123@10.0.0.1:7878":
                peer = n
                break
        assert peer is not None, "Registered peer not found in response"
        assert peer.get("node_id") == "abc123", f"Expected node_id='abc123', got '{peer.get('node_id')}'"

        await node.disconnect()
