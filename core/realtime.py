"""Realtime Activity ticks over Socket.IO (WebSocket)."""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

log = logging.getLogger("sqlmonitor.realtime")

_socketio: Any = None
_started = False
_lock = threading.Lock()

# How often to ping connected Activity clients (seconds)
TICK_SECONDS = 1.5


def init_realtime(dash_app) -> Any:
    """Attach Socket.IO to the Dash Flask server. Safe if package missing."""
    global _socketio, _started
    if _socketio is not None:
        return _socketio
    try:
        from flask_socketio import SocketIO, join_room, leave_room
    except ImportError:
        log.warning("flask-socketio not installed — Activity stays on Interval only")
        return None

    _socketio = SocketIO(
        dash_app.server,
        async_mode="threading",
        cors_allowed_origins="*",
        logger=False,
        engineio_logger=False,
        ping_interval=25,
        ping_timeout=60,
    )

    @_socketio.on("connect")
    def _on_connect():
        log.debug("socket connected")

    @_socketio.on("join_activity")
    def _on_join_activity(_data=None):
        join_room("activity")
        log.debug("joined activity room")

    @_socketio.on("leave_activity")
    def _on_leave_activity(_data=None):
        leave_room("activity")

    with _lock:
        if not _started:
            _started = True
            _socketio.start_background_task(_activity_tick_loop)

    return _socketio


def _activity_tick_loop():
    """Emit lightweight ticks; Dash clientside bumps store → load_activity."""
    while True:
        try:
            if _socketio is not None:
                _socketio.emit(
                    "activity_tick",
                    {"t": time.time()},
                    room="activity",
                    namespace="/",
                )
        except Exception:
            log.debug("activity tick emit failed", exc_info=True)
        if _socketio is not None:
            _socketio.sleep(TICK_SECONDS)
        else:
            time.sleep(TICK_SECONDS)


def run_server(dash_app, *, host: str, port: int, debug: bool = False) -> None:
    """Run with Socket.IO if available, else plain Dash."""
    sio = init_realtime(dash_app)
    if sio is None:
        dash_app.run(debug=debug, host=host, port=port)
        return
    # Dash 2+/3+/4: serve the Dash app via Flask under Socket.IO
    sio.run(
        dash_app.server,
        host=host,
        port=port,
        debug=debug,
        allow_unsafe_werkzeug=True,
        use_reloader=False,
    )
