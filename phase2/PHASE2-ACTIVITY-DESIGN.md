# Phase 2 — Activity Monitor Design

**Status:** Draft for review (no code until you say where to start)  
**Constraint:** No stored-procedure dependency. App uses **inline DMV queries** only, with the same connection model as today (SQL login + ODBC). Required permission for this module: `VIEW SERVER STATE` (and normal connect).

---

## 1. Goal

Turn the current Jobs-only app into a **multi-module SQL Server monitor**, starting with a polished **Activity** module that feels like a modern Activity Monitor:

| Tab | Purpose |
|-----|---------|
| **Blocking** | Who blocks whom, head blockers, wait time, queries |
| **WhoIsActive-style** | Rich live session snapshot (inspired by your `sp_WhoIsActive`, rewritten as our own query) |
| **Running Now** | Lightweight list of currently executing requests only |

Jobs module stays as-is and becomes tile #1 on the home screen.

---

## 2. Why not call your SPs?

You preferred **not** to grant SP execute rights.

So:

- Your `USP_RezaBlockingSessionV2` and `sp_WhoIsActive` are **reference designs only**.
- We implement **equivalent SELECT logic** inside the app (`db_activity.py`).
- No `EXEC` of objects in `SmartDBLog` / `SmartBISettingDB`.
- Works on any SQL Server where the login has `VIEW SERVER STATE`.

---

## 3. Home shell (visual first impression)

### Landing page

When the app opens (after connection is configured):

- Full-bleed dark hero / brand: **SQL Server Monitor** (or current product name)
- **6 large interactive tiles** (not a dense dashboard)
- Click a tile → enter that module
- Back control returns to home

| # | Tile | Phase |
|---|------|-------|
| 1 | Agent Jobs | Already built — wrap existing UI |
| 2 | Tables & Growth | Later |
| 3 | Indexes | Later |
| 4 | Activity Monitor | **Build now** |
| 5 | Disk & DB Health | Later |
| 6 | Wait Stats / Pulse | Later |

Tiles 2, 3, 5, 6 can show “Coming soon” until their phase.

### Design intent for tiles

- One strong visual composition (not a generic admin grid)
- Distinct icon + short title + one-line description
- Subtle motion on hover / enter
- Same dark RTL theme vocabulary as Phase 1 (Vazirmatn, teal accents)
- Activity tile can show a live badge count of current blockers when data is available

---

## 4. Activity module — three tabs

```
Home → Activity Monitor
         ├─ Blocking
         ├─ Live Sessions (WhoIsActive-style)
         └─ Running Now
```

### 4.1 Blocking

**Source logic:** rewritten from your blocking chain CTE (no SP).

Shows:

- Level / chain path
- Blocked session ↔ blocker session
- Head Blocker flag
- Wait type, wait resource, wait seconds/minutes
- Database, login, host, program (both sides)
- Blocked query text + blocker last query
- Open transaction count on blocker when available

**UI:**

- Summary strip: `# blockers`, `# blocked`, `max wait`
- Table (or expandable rows) with red emphasis on Head Blocker
- Empty state: “No blocking detected”

### 4.2 Live Sessions (WhoIsActive-style)

**Source logic:** our own DMV query inspired by WhoIsActive columns you care about — **not** embedding Adam Machanic’s full procedure.

Typical columns:

- session_id, status, login, host, program, database
- command, wait_type, wait_time, blocking_session_id
- CPU / reads / writes / elapsed (where cheap to get)
- sql_text (current statement)
- open_transaction_count

Filters (simple):

- Hide system sessions (default on)
- Hide sleeping without open tran (default on)
- Optional text search (login / host / program / sql)

### 4.3 Running Now

**Source logic:** lightweight `dm_exec_requests` + sessions + sql text.

Only sessions that currently have an active request (running / runnable / suspended).

Purpose: faster, cleaner “what is executing right now” without the full Live Sessions surface.

---

## 5. Refresh model (all three tabs)

Same pattern on every tab:

| Control | Behavior |
|---------|----------|
| **Refresh Now** | Manual fetch for the **active** tab only |
| **Auto-refresh** | Off / 5s / 10s / 30s / 60s |
| Scope | Only the open Activity tab polls; Jobs interval stays separate |

Also:

- Last refresh timestamp shown
- Loading indicator while query runs
- Error banner if DMV permission missing (`VIEW SERVER STATE`)

Optional later: header badge on Blocking tab when blockers > 0 (even while on another Activity tab).

---

## 6. Technical plan (implementation shape)

### Files (intended)

| File | Role |
|------|------|
| `app.py` | Add home shell + module switch; keep Jobs panel as module 1 |
| `db_activity.py` | New: Blocking / Live Sessions / Running Now queries |
| `assets/custom.css` | Home tiles + Activity tab styles |
| `phase2/queries/...` | Keep your originals as reference only |

### Data flow

```
Active tab + Refresh Now / Interval
    → db_activity.get_*()
    → dcc.Store
    → render table for that tab
```

### Permissions message (Settings)

Extend “required permissions” note:

- Existing: SELECT on msdb job tables
- New for Activity: `VIEW SERVER STATE`

No new database install step. No SP deploy step.

---

## 7. What we will NOT do in this first Activity slice

- Call `sp_WhoIsActive` or `USP_RezaBlockingSessionV2`
- Kill session / kill query buttons (can be Phase 2.1 if you want)
- Query store / wait stats module (tile 6 later)
- Tables / Indexes / Disk modules

---

## 8. Suggested build order (you choose start point)

1. **Home shell + 6 tiles** (Jobs opens existing UI; Activity opens empty shell)
2. **Activity tabs chrome** (3 tabs + Refresh Now + interval dropdown)
3. **Running Now** query + table (simplest)
4. **Blocking** query + table (your CTE logic, inline)
5. **Live Sessions** query + filters + table
6. Visual polish (tile motion, badges, empty/error states)

---

## 9. Success criteria

- User opens app → sees memorable 6-tile home
- Enters Activity → three clear tabs
- Can refresh manually or set interval like Activity Monitor
- Blocking chain readable and Head Blocker obvious
- Works with current login **without** SP execute rights
- Jobs monitoring still works unchanged

---

## 10. Open decision for you

Tell me where to start:

- **A)** Home tiles first  
- **B)** Activity tabs + Running Now first (no home yet)  
- **C)** Full Activity (all 3 tabs) first, home shell after  
- **D)** Something else (specify)

After you pick, implementation starts from that point only.
