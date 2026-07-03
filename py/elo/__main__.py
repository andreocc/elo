"""Elo CLI — gerenciamento de identidade e status do nó.

Uso:
    python -m elo status              # Status completo (id, chaves)
    python -m elo id                  # Apenas o node_id
    python -m elo pubkey              # Chave pública completa
    python -m elo init                # Gera e salva identidade persistente
    python -m elo serve               # Inicia um nó interativo
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path

from elo.security import (
    EphemeralIdentity,
    generate_and_save_identity,
    load_identity,
    pubkey_to_id,
    DEFAULT_KEY_DIR,
)


def _short_id(node_id: str, n: int = 12) -> str:
    h = hashlib.sha256(node_id.encode()).hexdigest()[:16]
    return f"{node_id[:n]}... (sha256:{h})"


def cmd_status() -> None:
    """Exibe o status completo do nó (identidade, chaves)."""
    seed_path = DEFAULT_KEY_DIR / "identity.seed"
    has_persisted = False
    if seed_path.exists():
        try:
            identity = load_identity()
            has_persisted = True
        except Exception:
            identity = EphemeralIdentity()
    else:
        identity = EphemeralIdentity()

    node_id = identity.node_id
    pubkey_bytes = identity.public_key.public_bytes_raw()

    print("=" * 52)
    print("  ELO NODE STATUS")
    print("=" * 52)
    print(f"  Node ID:    {node_id}")
    print(f"  Hash:       {_short_id(node_id)}")
    print("-" * 52)
    print(f"  Algorithm:  ed25519")
    print("-" * 52)
    print(f"  Public key (hex):")
    print(f"  {pubkey_bytes.hex()}")
    print(f"  Public key (b64):")
    print(f"  {node_id}")
    print("-" * 52)

    if has_persisted:
        print(f"  Persisted:  {DEFAULT_KEY_DIR}")
        print(f"  Saved ID:   {node_id}")
    else:
        print(f"  Persisted:  no (ephemeral)")
        print(f"  Use 'python -m elo init' to save")
        print(f"  Default dir: {DEFAULT_KEY_DIR}")

    print("=" * 52)


def cmd_id() -> None:
    seed_path = DEFAULT_KEY_DIR / "identity.seed"
    if seed_path.exists():
        try:
            identity = load_identity()
        except Exception:
            identity = EphemeralIdentity()
    else:
        identity = EphemeralIdentity()
    print(identity.node_id)


def cmd_pubkey() -> None:
    seed_path = DEFAULT_KEY_DIR / "identity.seed"
    if seed_path.exists():
        try:
            identity = load_identity()
        except Exception:
            identity = EphemeralIdentity()
    else:
        identity = EphemeralIdentity()
    node_id = identity.node_id
    pubkey = identity.public_key.public_bytes_raw()
    print(f"node_id (b64):  {node_id}")
    print(f"public (hex):   {pubkey.hex()}")
    print(f"algorithm:      ed25519")


def cmd_init() -> None:
    key_dir = DEFAULT_KEY_DIR
    pub, priv = generate_and_save_identity(key_dir)
    node_id = pubkey_to_id(pub)
    print(f"Identity generated and saved to: {key_dir}")
    print(f"  identity.seed -- ed25519 private key")
    print()
    print(f"Node ID: {node_id}")
    print(f"Hash:    {_short_id(node_id)}")
    print()
    print("!! Keep identity.seed safe -- it is your node's identity.")
    print("   Without it, peers will not recognize this node after restart.")


def cmd_serve(args: argparse.Namespace) -> None:
    from elo import Node

    peers_list = [p.strip() for p in args.peers.split(",")] if args.peers else None

    # Load persistent identity if exists, otherwise Node() will generate ephemeral
    identity = None
    seed_path = DEFAULT_KEY_DIR / "identity.seed"
    if seed_path.exists():
        try:
            identity = load_identity()
        except Exception:
            pass

    async def _serve():
        node = Node(
            args.name,
            port=args.port,
            peers=peers_list,
            tracker=args.tracker or "public",
            identity=identity
        )
        await node.connect()
        await node.register(agents=[args.name + "-agent"])

        @node.on_task
        async def handle(task):
            print(f"[task] {task.capability}: {task.payload}")
            return {"echo": task.payload, "from": node.node_id}

        print(f"[elo] serving on port {node.port} | id={_short_id(node.node_id)}")
        print(f"[elo] Press Ctrl+C to stop")
        await node.run()

    try:
        asyncio.run(_serve())
    except KeyboardInterrupt:
        print("\n[elo] stopped")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="elo",
        description="Elo CLI — malha P2P para agentes de IA",
    )
    sub = parser.add_subparsers(dest="command", help="Comandos")

    sub.add_parser("status", help="Status completo do nó (identidade + chaves)")
    sub.add_parser("id", help="Apenas o node_id")
    sub.add_parser("pubkey", help="Chave pública em formatos úteis")
    sub.add_parser("init", help="Gerar e salvar identidade persistente")
    
    serve_parser = sub.add_parser("serve", help="Iniciar um nó interativo")
    serve_parser.add_argument("--name", default="elo-node", help="Nome do nó")
    serve_parser.add_argument("--port", type=int, default=7878, help="Porta TCP")
    serve_parser.add_argument("--peers", help="Peers iniciais separados por vírgula")
    serve_parser.add_argument("--tracker", help="Tracker visibility ou tracker host")

    args = parser.parse_args()

    commands = {
        "status": cmd_status,
        "id": cmd_id,
        "pubkey": cmd_pubkey,
        "init": cmd_init,
    }

    if args.command == "serve":
        cmd_serve(args)
    elif args.command in commands:
        commands[args.command]()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
