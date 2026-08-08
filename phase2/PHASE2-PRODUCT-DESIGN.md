# Phase 2 — Product Design (v4 — Locked)

**Status:** Wave 0 started — lean foundation + Home shell + Running Now live  
**Product mantra:** *Build the SQL Server Monitor first. Design the Monitoring Platform later.*

Insight Discovery (Metric Store / Today's Insights / Email) is documented in
`phase2/INSIGHT-ROADMAP.md` and starts **after** Live Monitor V1 polish is done.

---

## Project law (non-negotiable for Wave 0 / Wave 1)

> **In Wave 0 and Wave 1, no feature outside SQL Server Activity Core is implemented. Only extension points are defined.**

| Allowed | Forbidden in Wave 0–1 |
|---------|------------------------|
| SQL Server DMV queries | Azure / Postgres / multi-DB providers |
| One SQL Server connection | Real multi-server switching logic |
| Activity: Running / Blocking / Session Details | Alert delivery (Telegram/email/etc.) |
| Refresh / Pause / active-tab only | Event store / Timeline history UI |
| Severity + theme tokens | Snapshot compare |
| Friendly permission errors | Latency probes, Kill, Plans, Locks |
| Stub interfaces / empty models | Second product surfaces |

---

## Why this law exists

1. **Multi-provider now = Multi-Database product** — DMVs, blocking, waits, permissions differ completely. Interface yes; second provider no.
2. **Real Alert Engine** = rules + storage + channels + scheduling — its own product. Activity may emit a simple event dict later; nothing consumes it in Wave 1.
3. **Timeline** becomes Event Store + history module. MVP only needs *Last Refresh* + *Current State*.
4. Goal: usable Activity Monitor in **weeks**, not months.

---

## Wave 0 — Foundation only

```
core/
  providers/
    base.py                 # DatabaseProvider interface (methods only)
    sqlserver_provider.py   # ONLY concrete provider
  connection.py             # single active server (model ready for later list)
  refresh.py                # interval / pause / active target
  permissions.py            # VIEW SERVER STATE etc. + grant hint text
  severity.py               # healthy/warning/important/critical
  contracts.py              # status/severity/summary/rows/timestamp
  logging_setup.py          # logs/ (gitignore)
  registry.py               # simple module list for Home (minimal)
modules/
  home/                     # may wait until end of Wave 0 / start Wave 1
  jobs/                     # extract existing jobs (thin move)
  activity/                 # shell only if needed; real tabs in Wave 1
assets/                     # severity + theme tokens
logs/                       # gitignored
```

### Provider interface (extension point only)

```python
class DatabaseProvider(Protocol):
    def get_running_requests(self) -> QueryResult: ...
    def get_blocking(self) -> QueryResult: ...
    def get_sessions(self) -> QueryResult: ...
```

Concrete now: `SqlServerProvider` only.

### Explicit stubs (define, do not build)

| Feature | Wave 0–1 action |
|---------|-----------------|
| Multi-DB / Multi-server | Connection model may hold `servers=[one]`; no switcher logic |
| Alert | Optional tiny event dict shape in comments/models — unused |
| Timeline | Not built — only last refresh timestamp in UI |
| Snapshot | Not built |
| Latency | Not built |

---

## Wave 1 — Activity Core (usable product)

1. Home shell (6 tiles; Jobs works; Activity opens; others “Coming soon”)
2. Fixed header: product name, server, Connected, last refresh, refresh interval
3. Activity tabs: **Running Now** | **Blocking** | *(Live Sessions can be Wave 1b if time)*
4. Health strip summaries from `QueryResult.summary`
5. Session Details panel (click row)
6. Refresh Now + Auto interval + Pause (active tab only)
7. Empty state / Permission error state
8. Truncated SQL + View SQL (minimal)
9. Jobs module unchanged in behavior

**Recommended Wave 1 scope (strict):**

- Running Now  
- Blocking  
- Session Details  
- Refresh controls  

Live Sessions, Search chips, Export, Badge, Copy — **Wave 1b / Wave 2** after core feels solid.

---

## Standard result contract (keep)

```json
{
  "status": "ok | empty | error | permission_denied",
  "severity": "healthy | warning | important | critical",
  "summary": {},
  "rows": [],
  "timestamp": "...",
  "meta": { "row_count": 0, "capped": false, "hint": null }
}
```

---

## Deferred (approved ideas, not Wave 0–1 work)

- Snapshot / Compare  
- Event Timeline / Event Store  
- Real Alert Engine + notifications  
- Multi-server + multi-provider  
- Column picker, Freeze row, Excel export  
- Kill / Locks / Plans / Query Store  
- Home tile rich KPIs beyond simple counts if expensive  

---

## Success criteria

**Wave 0 done:** folder layout + SqlServerProvider + connection/refresh/permissions/severity/contracts/logging; app still boots; Jobs still works.

**Wave 1 done:** user can open Activity, see Running + Blocking, refresh/pause, open session details, see clear empty/error — without any SP execute rights.

---

## Start command

Reply:

- **Start Wave 0**  
- or **Start Wave 0 then Wave 1 continuous**

Then implementation begins under this law only.
