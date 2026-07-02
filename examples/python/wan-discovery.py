"""WAN Test: connect to tracker, discover peers, send tasks."""
import asyncio, sys
sys.path.insert(0, "..")
from elo import Node

TRACKER = "100.91.215.113:7878"  # SAM Tailscale IP

async def main():
    node = Node("wan-tester", port=0, peers=[TRACKER])
    await node.connect()
    await node.register(agents=["ping"])

    @node.on_task
    async def handle(task):
        return {"pong": task.payload, "from": node.node_id[:12]}

    # Discover peers via tracker
    print("🔍 Discovering peers...")
    result = await node.send_task("", "discovery", {})
    if result.status == "success":
        peers = result.payload.get("known_peers", [])
        print(f"📡 Tracker: {result.payload.get('tracker_id')}")
        print(f"👥 Peers: {result.payload.get('peers_connected')}")
        for p in peers:
            print(f"   • {p['addr']} — {p['caps']}")
    else:
        print(f"❌ Discovery failed: {result.error}")

    await node.disconnect()

asyncio.run(main())
