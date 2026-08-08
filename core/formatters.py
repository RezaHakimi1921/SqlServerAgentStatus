"""Display formatters — keep UI numbers / durations consistent (WhoIsActive-friendly)."""
from __future__ import annotations

from typing import Any, Optional, Union

Number = Union[int, float]


def fmt_int(value: Any, *, default: str = "0") -> str:
    """Thousand-separated integer, e.g. 106657611 → 106,657,611."""
    if value is None or value == "":
        return default
    try:
        n = int(float(value))
    except (TypeError, ValueError):
        return str(value)
    # Western grouping; readable in LTR SQL metric columns
    return f"{n:,}"


def fmt_compact(value: Any, *, default: str = "0") -> str:
    """Compact metric label: 41900 → 41.9K, 4800000 → 4.8M."""
    if value is None or value == "":
        return default
    try:
        n = float(value)
    except (TypeError, ValueError):
        return str(value)
    sign = "-" if n < 0 else ""
    n = abs(n)
    if n >= 1_000_000_000:
        return f"{sign}{n / 1_000_000_000:.1f}B".replace(".0B", "B")
    if n >= 1_000_000:
        return f"{sign}{n / 1_000_000:.1f}M".replace(".0M", "M")
    if n >= 1_000:
        return f"{sign}{n / 1_000:.1f}K".replace(".0K", "K")
    if n == int(n):
        return f"{sign}{int(n)}"
    return f"{sign}{n:.1f}"


def fmt_size_mb(mb: Any, *, default: str = "—") -> str:
    """Display size from megabytes: 189 → 189 MB, 2300 → 2.3 GB."""
    if mb is None or mb == "":
        return default
    try:
        v = float(mb)
    except (TypeError, ValueError):
        return default
    if v >= 1024:
        return f"{v / 1024:.1f} GB".replace(".0 GB", " GB")
    if v >= 100:
        return f"{v:.0f} MB"
    return f"{v:.1f} MB".replace(".0 MB", " MB")


def fmt_float(value: Any, *, digits: int = 1, default: str = "0") -> str:
    if value is None or value == "":
        return default
    try:
        n = float(value)
    except (TypeError, ValueError):
        return str(value)
    formatted = f"{n:,.{digits}f}"
    return formatted


def fmt_elapsed_whois(ms: Any) -> str:
    """WhoIsActive-style elapsed: dd hh:mm:ss.mss (from milliseconds)."""
    try:
        total_ms = max(0, int(ms or 0))
    except (TypeError, ValueError):
        return "00 00:00:00.000"
    days, rem = divmod(total_ms, 86_400_000)
    hours, rem = divmod(rem, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    seconds, millis = divmod(rem, 1000)
    return f"{days:02d} {hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


def fmt_duration_hms(ms: Any) -> str:
    """Clock from milliseconds as HH:MM:SS (hours may exceed 24; no days/ms)."""
    try:
        total_ms = max(0, int(ms or 0))
    except (TypeError, ValueError):
        return "—"
    total = total_ms // 1000
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def fmt_running_label(ms: Any) -> str:
    """Human label: 5m 12s / 1h 2m 3s."""
    try:
        total_ms = max(0, int(ms or 0))
    except (TypeError, ValueError):
        return "—"
    total = total_ms // 1000
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"
