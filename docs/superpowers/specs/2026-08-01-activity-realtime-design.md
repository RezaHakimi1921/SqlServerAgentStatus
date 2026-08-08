# Activity Realtime + Lookup Charts — Design

**Date:** 2026-08-01  
**Scope:** Places that already feel “Live” — Activity Monitor (Running / Blocking / Lookup). Jobs stays on Interval.

## Goals

1. **No white blank** on first open — static boot splash in raw HTML before Dash/React loads.
2. **Progress split**
   - Lookup main page → **whole transaction / session** progress (rows, all PRINT messages).
   - View Statement → **current statement** progress (focused statement + `% complete` + same live message feed for that SPID).
3. **Line charts** (Plotly) on Lookup — four metrics; each chart: **server** series + **this session** series (second color).
4. **WebSocket ticks** drive Activity refresh instead of (or as primary over) coarse Interval polling.

## Approach

| Piece | Choice |
|-------|--------|
| Boot splash | Inline `#boot-splash` in `app.index_string` + CSS; hide when React `app-splash` takes over / app ready |
| Charts | `dcc.Graph` Plotly scatter lines; dual traces per panel |
| Session series | Append deltas from lookup row (`cpu_time`, `reads`, `writes`, `progress.rows_done`) beside server pulse |
| Transport | `flask-socketio` on `app.server`; emit `activity_tick` ~1–2s when clients connected; clientside `set_props` on `store-ws-tick` → existing `load_activity` |
| Interval | Keep as fallback (slower, e.g. 30s) or disable while WS connected |

## Out of scope

- Jobs / Insights full WebSocket migration
- Rewriting Metric Store collector

## Success

- Opening `localhost:8050` shows spinner within first paint (no multi-second white screen).
- Lookup shows large readable line charts with server vs session.
- Statement modal progress is statement-scoped; main card is transaction-scoped.
- Activity tabs update via WS tick while Live / not paused.
