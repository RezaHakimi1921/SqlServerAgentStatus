"""Active-target refresh helpers (module/tab scoped). Extension point only for multi-server."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


ACTIVITY_INTERVALS_SEC = (0, 5, 10, 30, 60)  # 0 = off


@dataclass
class RefreshState:
    paused: bool = False
    interval_sec: int = 10
    active_module: str = "home"
    active_tab: Optional[str] = None

    def should_poll(self, module: str, tab: Optional[str] = None) -> bool:
        if self.paused or self.interval_sec <= 0:
            return False
        if module != self.active_module:
            return False
        if tab is not None and self.active_tab is not None and tab != self.active_tab:
            return False
        return True

    def interval_ms(self) -> int:
        # Dash Interval minimum; use large value when off/paused and disable separately
        sec = self.interval_sec if self.interval_sec > 0 else 3600
        return sec * 1000
