"""Store SQL passwords in Windows Credential Manager (via keyring)."""

import keyring

SERVICE = "SqlServerAgentStatus"


def _account_key(server: str, user: str) -> str:
    return f"{server.strip()}|{user.strip()}"


def get_sql_password(server: str, user: str) -> str:
    if not server or not user:
        return ""
    return keyring.get_password(SERVICE, _account_key(server, user)) or ""


def set_sql_password(server: str, user: str, password: str) -> None:
    keyring.set_password(SERVICE, _account_key(server, user), password)


def delete_sql_password(server: str, user: str) -> None:
    try:
        keyring.delete_password(SERVICE, _account_key(server, user))
    except keyring.errors.PasswordDeleteError:
        pass


def _notification_key(target_id: str) -> str:
    return f"notification|{target_id.strip()}"


def get_notification_secret(target_id: str) -> str:
    """Read SMTP password or webhook HMAC key from the OS keyring."""
    if not target_id:
        return ""
    return keyring.get_password(SERVICE, _notification_key(target_id)) or ""


def set_notification_secret(target_id: str, secret: str) -> None:
    """Store a notification secret in the OS keyring, never in app config/SQLite."""
    if not target_id or not secret:
        raise ValueError("target_id and secret are required")
    keyring.set_password(SERVICE, _notification_key(target_id), secret)


def delete_notification_secret(target_id: str) -> None:
    try:
        keyring.delete_password(SERVICE, _notification_key(target_id))
    except keyring.errors.PasswordDeleteError:
        pass
