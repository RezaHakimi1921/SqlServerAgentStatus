"""Shared severity levels for all modules."""

HEALTHY = "healthy"
WARNING = "warning"
IMPORTANT = "important"
CRITICAL = "critical"

SEVERITY_LABELS = {
    HEALTHY: "Healthy",
    WARNING: "Warning",
    IMPORTANT: "Important",
    CRITICAL: "Critical",
}

SEVERITY_CSS = {
    HEALTHY: "sev-healthy",
    WARNING: "sev-warning",
    IMPORTANT: "sev-important",
    CRITICAL: "sev-critical",
}


def classify_wait_ms(wait_ms: int) -> str:
    if wait_ms is None:
        return HEALTHY
    if wait_ms >= 300_000:
        return CRITICAL
    if wait_ms >= 60_000:
        return IMPORTANT
    if wait_ms >= 10_000:
        return WARNING
    return HEALTHY


def worst(*levels: str) -> str:
    order = {HEALTHY: 0, WARNING: 1, IMPORTANT: 2, CRITICAL: 3}
    best = HEALTHY
    for level in levels:
        if order.get(level, 0) > order.get(best, 0):
            best = level
    return best
