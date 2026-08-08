"""Simple module registry for Home tiles. Extension point for plugin discovery later."""
from __future__ import annotations

from typing import Dict, List, Optional


MODULES: List[Dict] = [
    {
        "id": "jobs",
        "title": "Agent Jobs",
        "subtitle": "Running jobs, history, Gantt",
        "icon": "⚡",
        "status": "ready",
    },
    {
        "id": "activity",
        "title": "Activity Monitor",
        "subtitle": "Running, blocking, sessions",
        "icon": "◎",
        "status": "ready",
    },
    {
        "id": "insights",
        "title": "Today's Insights",
        "subtitle": "What mattered today (Metric Store)",
        "icon": "✦",
        "status": "ready",
    },
    {
        "id": "docs",
        "title": "Documentation",
        "subtitle": "Status, Wait, Progress, Insights…",
        "icon": "?",
        "status": "ready",
    },
    {
        "id": "settings",
        "title": "Settings",
        "subtitle": "Connection, metrics, refresh",
        "icon": "⚙",
        "status": "ready",
    },
    {
        "id": "tables",
        "title": "Tables & Growth",
        "subtitle": "Space, heaps & growth history",
        "icon": "▤",
        "status": "ready",
    },
    {
        "id": "indexes",
        "title": "Indexes",
        "subtitle": "Object Intelligence — tables, indexes & triage",
        "icon": "▥",
        "status": "ready",
    },
    {
        "id": "disk",
        "title": "Disk & DB Health",
        "subtitle": "Files, free space, backups",
        "icon": "◉",
        "status": "soon",
    },
    {
        "id": "waits",
        "title": "Wait Stats",
        "subtitle": "Performance pulse",
        "icon": "◈",
        "status": "soon",
    },
]


def list_modules() -> List[Dict]:
    return list(MODULES)


def get_module(module_id: str) -> Optional[Dict]:
    for m in MODULES:
        if m["id"] == module_id:
            return m
    return None
