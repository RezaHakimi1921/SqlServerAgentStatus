"""Permission checks and grant hints (SQL Server only for Wave 0/1)."""
from __future__ import annotations

VIEW_SERVER_STATE_HINT = (
    "VIEW SERVER STATE permission is required.\n\n"
    "Your login can only see its own session, so Activity looks empty.\n\n"
    "Grant (run as admin on SQL Server):\n"
    "GRANT VIEW SERVER STATE TO [AgentGraph];"
)

INDEX_PERMISSIONS_HINT = (
    "Indexes needs database-level rights on the selected database.\n\n"
    "Server (database list):\n"
    "  GRANT VIEW ANY DATABASE TO [YourLogin];\n\n"
    "Per database (example RasBankAccountingCloud):\n"
    "  USE [RasBankAccountingCloud];\n"
    "  CREATE USER [YourLogin] FOR LOGIN [YourLogin];  -- if missing\n"
    "  GRANT VIEW DEFINITION TO [YourLogin];\n"
    "  GRANT VIEW DATABASE STATE TO [YourLogin];\n\n"
    "See INSTALL.md → Indexes module."
)


def is_permission_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    needles = (
        "permission",
        "view server state",
        "denied",
        "not authorized",
        "cannot view",
    )
    return any(n in msg for n in needles)


def permission_hint_for(exc: BaseException) -> str:
    if is_permission_error(exc):
        return VIEW_SERVER_STATE_HINT
    return str(exc)


def has_view_server_state(conn) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT HAS_PERMS_BY_NAME(null, null, 'VIEW SERVER STATE')")
    row = cur.fetchone()
    return bool(row and row[0])
