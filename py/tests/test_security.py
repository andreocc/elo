"""Testes do módulo de segurança Elo — NKEYS, assinatura."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from elo.security import (
    EphemeralIdentity,
    generate_and_save_identity,
    generate_identity,
    id_to_pubkey,
    load_identity,
    pubkey_to_id,
    sign_message,
    verify_signature,
)


class TestKeyGeneration:
    """Testes de geração de chaves."""

    def test_generate_ed25519(self):
        priv, pub = generate_identity()
        assert priv is not None
        assert pub is not None
        raw = pub.public_bytes_raw()
        assert len(raw) == 32  # ed25519 public key

    def test_pubkey_id_roundtrip(self):
        _, pub = generate_identity()
        node_id = pubkey_to_id(pub)
        assert len(node_id) > 20
        pub2 = id_to_pubkey(node_id)
        assert pub.public_bytes_raw() == pub2.public_bytes_raw()


class TestSigning:
    """Testes de assinatura e verificação."""

    def test_sign_and_verify(self):
        priv, pub = generate_identity()
        payload = {"msg": "hello", "num": 42}
        sig = sign_message(priv, payload)
        assert len(sig) > 40
        assert verify_signature(pub, payload, sig)

    def test_tampered_payload(self):
        priv, pub = generate_identity()
        payload = {"msg": "hello"}
        sig = sign_message(priv, payload)
        payload["msg"] = "tampered"
        assert not verify_signature(pub, payload, sig)

    def test_wrong_key(self):
        priv, _ = generate_identity()
        _, wrong_pub = generate_identity()
        payload = {"msg": "hello"}
        sig = sign_message(priv, payload)
        assert not verify_signature(wrong_pub, payload, sig)

    def test_canonical_json(self):
        """Assinatura independe da ordem das chaves."""
        priv, pub = generate_identity()
        a = {"a": 1, "b": 2}
        b = {"b": 2, "a": 1}
        sig = sign_message(priv, a)
        assert verify_signature(pub, b, sig)


class TestEphemeralIdentity:
    """Testes da identidade efêmera."""

    def test_create(self):
        identity = EphemeralIdentity()
        assert identity.node_id is not None
        assert len(identity.node_id) > 20
        assert identity.private_key is not None

    def test_sign_and_verify_own(self):
        identity = EphemeralIdentity()
        payload = {"test": True}
        sig = identity.sign(payload)
        assert identity.verify(payload, sig)


class TestPersistedIdentity:
    """Testes de persistência de identidade em disco."""

    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            key_dir = Path(tmp)

            # Gera e salva
            pub, priv = generate_and_save_identity(key_dir)
            node_id = pubkey_to_id(pub)

            seed_file = key_dir / "identity.seed"
            assert seed_file.exists()
            # permissão 0o600 (Unix apenas — Windows ignora chmod)
            import os as _os
            if _os.name != "nt":
                assert (seed_file.stat().st_mode & 0o777) == 0o600

            # Carrega
            loaded_identity = load_identity(key_dir)
            assert loaded_identity is not None
            loaded_pub = loaded_identity.public_key
            assert pubkey_to_id(loaded_pub) == node_id

            # Assina com a carregada, verifica com a original
            sig = loaded_identity.sign({"test": True})
            assert verify_signature(pub, {"test": True}, sig)

    def test_load_missing_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            key_dir = Path(tmp)
            with pytest.raises(FileNotFoundError):
                load_identity(key_dir)
