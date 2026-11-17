"""Provider accessor — safe to import without loading SqlServerProvider eagerly."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.providers.sqlserver_provider import SqlServerProvider

_provider = None


def get_provider():
    global _provider
    if _provider is None:
        from core.providers.sqlserver_provider import SqlServerProvider

        _provider = SqlServerProvider()
    return _provider


def reset_provider() -> None:
    global _provider
    _provider = None
