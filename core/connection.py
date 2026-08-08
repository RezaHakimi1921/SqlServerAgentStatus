"""Connection helpers. Multi-server model is an extension point; one active server now."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from config import is_configured, load_config
from db import get_connection


def active_server_info() -> Dict[str, Any]:
    cfg = load_config()
    return {
        "id": "default",
        "name": cfg.get("server") or "Not configured",
        "server": cfg.get("server") or "",
        "database": cfg.get("database") or "msdb",
        "user": cfg.get("user") or "",
        "configured": is_configured(),
    }


def list_servers() -> List[Dict[str, Any]]:
    """Extension point: later return multiple entries. Today only one."""
    info = active_server_info()
    return [info] if info["configured"] else []


def connect(config: Optional[dict] = None):
    return get_connection(config)
