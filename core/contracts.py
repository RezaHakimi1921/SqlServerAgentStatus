"""Standard result contract for all provider/service calls."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


SEVERITIES = ("healthy", "warning", "important", "critical")
STATUSES = ("ok", "empty", "error", "permission_denied")


@dataclass
class QueryResult:
    status: str = "ok"
    severity: str = "healthy"
    summary: Dict[str, Any] = field(default_factory=dict)
    rows: List[Dict[str, Any]] = field(default_factory=list)
    timestamp: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        self.meta.setdefault("row_count", len(self.rows))
        self.meta.setdefault("capped", False)
        self.meta.setdefault("hint", None)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def empty(cls, summary: Optional[Dict[str, Any]] = None, severity: str = "healthy") -> "QueryResult":
        return cls(status="empty", severity=severity, summary=summary or {}, rows=[])

    @classmethod
    def error(cls, message: str, *, permission_denied: bool = False, hint: str = None) -> "QueryResult":
        status = "permission_denied" if permission_denied else "error"
        severity = "critical" if permission_denied else "important"
        return cls(
            status=status,
            severity=severity,
            summary={},
            rows=[],
            meta={"hint": hint or message, "error_code": status, "row_count": 0, "capped": False},
        )
