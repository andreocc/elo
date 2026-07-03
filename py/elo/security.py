"""Módulo de segurança do Elo — NKEYS, assinatura.

Camadas:
1. Geração e armazenamento de identidade (ed25519)
2. Assinatura de mensagens (prova de autoria)
3. Verificação de assinaturas
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any


from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

# ── Caminho padrão da identidade ──────────────────────────

DEFAULT_KEY_DIR = Path.home() / ".elo"


# ── Geração de identidade ──────────────────────────────────


def generate_identity() -> tuple[ed25519.Ed25519PrivateKey, ed25519.Ed25519PublicKey]:
    """Gera um par de chaves ed25519 para identidade do nó.

    Returns:
        (private_key, public_key)
    """
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    return private_key, public_key


# ── Codificação/decodificação ──────────────────────────────


def pubkey_to_id(public_key: ed25519.Ed25519PublicKey) -> str:
    """Converte chave pública ed25519 em node_id (base64 URL-safe sem padding)."""
    raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def id_to_pubkey(node_id: str) -> ed25519.Ed25519PublicKey:
    """Converte node_id de volta para chave pública ed25519."""
    raw = base64.urlsafe_b64decode(node_id + "==")
    return ed25519.Ed25519PublicKey.from_public_bytes(raw)


# ── Armazenamento de identidade ────────────────────────────


def _chmod_0600(path: Path) -> None:
    """Define permissão 0o600 no arquivo (Unix). No-op no Windows."""
    try:
        path.chmod(0o600)
    except NotImplementedError:
        pass


def save_identity(
    private_key: ed25519.Ed25519PrivateKey,
    key_dir: Path = DEFAULT_KEY_DIR,
) -> Path:
    """Salva a identidade do nó em disco.

    Args:
        private_key: Chave privada ed25519.
        key_dir: Diretório para salvar os arquivos.

    Returns:
        Caminho do arquivo de seed salvo.
    """
    key_dir.mkdir(parents=True, exist_ok=True)

    # Salva seed ed25519 (PKCS#8 PEM)
    seed_path = key_dir / "identity.seed"
    seed = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    seed_path.write_bytes(seed)
    _chmod_0600(seed_path)

    return seed_path


def load_identity(
    key_dir: Path = DEFAULT_KEY_DIR,
) -> EphemeralIdentity:
    """Carrega a identidade do nó do disco."""
    return EphemeralIdentity.from_file(key_dir)



def generate_and_save_identity(
    key_dir: Path = DEFAULT_KEY_DIR,
) -> tuple[ed25519.Ed25519PublicKey, ed25519.Ed25519PrivateKey]:
    """Gera e salva identidade (ed25519).

    Returns:
        (public_key, private_key)
    """
    private_key, public_key = generate_identity()
    save_identity(private_key, key_dir)
    return public_key, private_key


# ── Assinatura de mensagens ────────────────────────────────


def sign_message(private_key: ed25519.Ed25519PrivateKey, payload: dict[str, Any]) -> str:
    """Assina um payload com a chave privada ed25519.

    O payload é canonicalizado como JSON compacto antes de assinar.

    Args:
        private_key: Chave privada do nó.
        payload: Dicionário a ser assinado.

    Returns:
        Assinatura em base64 URL-safe.
    """
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    signature = private_key.sign(canonical)
    return base64.urlsafe_b64encode(signature).rstrip(b"=").decode()


def verify_signature(
    public_key: ed25519.Ed25519PublicKey,
    payload: dict[str, Any],
    signature_b64: str,
) -> bool:
    """Verifica a assinatura de um payload.

    Args:
        public_key: Chave pública do remetente.
        payload: Dicionário original.
        signature_b64: Assinatura em base64 URL-safe.

    Returns:
        True se a assinatura for válida.
    """
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    try:
        sig = base64.urlsafe_b64decode(signature_b64 + "==")
        public_key.verify(sig, canonical)
        return True
    except Exception:
        return False


# ── Utilitário de identidade efêmera (sem disco) ───────────


@dataclass
class EphemeralIdentity:
    """Identidade temporária — útil para testes ou nós sem persistência."""
    sensitive: bool = field(default=True, init=False)

    def __init__(self) -> None:
        self._private_key, self._public_key = generate_identity()
        self.sensitive = True

    @classmethod
    def from_file(cls, key_dir: Path = DEFAULT_KEY_DIR) -> EphemeralIdentity:
        """Carrega uma identidade do disco."""
        seed_path = key_dir / "identity.seed"
        if not seed_path.exists():
            raise FileNotFoundError(
                f"Identidade não encontrada em {seed_path}. "
                "Use elo.security.generate_and_save_identity() primeiro."
            )

        private_key: ed25519.Ed25519PrivateKey = serialization.load_pem_private_key(
            seed_path.read_bytes(),
            password=None,
        )  # type: ignore[assignment]

        identity = cls.__new__(cls)
        identity._private_key = private_key
        identity._public_key = private_key.public_key()
        identity.sensitive = True
        return identity

    @property
    def node_id(self) -> str:
        return pubkey_to_id(self._public_key)

    @property
    def private_key(self) -> ed25519.Ed25519PrivateKey:
        return self._private_key

    @property
    def public_key(self) -> ed25519.Ed25519PublicKey:
        return self._public_key

    def sign(self, payload: dict[str, Any]) -> str:
        return sign_message(self._private_key, payload)

    def verify(self, payload: dict[str, Any], signature: str) -> bool:
        return verify_signature(self._public_key, payload, signature)
