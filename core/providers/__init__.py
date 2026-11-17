"""Package marker for providers — get_provider is cycle-safe via factory."""
from core.providers.factory import get_provider, reset_provider

__all__ = ["SqlServerProvider", "get_provider", "reset_provider"]


def __getattr__(name: str):
    if name == "SqlServerProvider":
        from core.providers.sqlserver_provider import SqlServerProvider

        return SqlServerProvider
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
