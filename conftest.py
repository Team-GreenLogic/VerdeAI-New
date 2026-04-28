"""Root pytest configuration."""

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "e2e: mark test as requiring a running Docker stack")
