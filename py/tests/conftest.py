"""Configuração do pytest para Elo."""

import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: marca testes que precisam de NATS rodando",
    )
