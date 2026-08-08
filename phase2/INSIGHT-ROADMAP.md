# Insight Discovery Roadmap

**Status:** Locked direction — implement after Live Monitor V1 is finished  
**Product mantra:** Live Monitor first. Insight Discovery next. Email last (infra ready early).

---

## Product identity

Insight Discovery — not Health Score, not statistical correlation, not just more charts.

In 30 seconds the product should answer:

1. What is unusual today?
2. Since when?
3. What is the likely cause?
4. Should I act now?

**Live Monitor** = what is happening right now (real-time DMVs).  
**Insights** = what mattered today (aggregation over Metric Store).  
These must never show the same table/query.

---

## Phase map (aligned with current project)

| Phase | Focus | Notes |
|-------|--------|------|
| **V1 — Live Monitor (now)** | Jobs + Activity (Running / Blocking / Session Lookup), color depth, green neon UI | Finish this before Insight UI |
| **V2 — Insight Discovery** | Metric Store + Scheduler + Rule Templates + Today's Insights (in-app) | No email required for value |
| **V2.5 — Baseline + Association** | Silent Baseline+2σ upgrade; Event Association; Historical Discovery; Persian sentences | |
| **V3 — Depth** | Root Cause Hint, Timeline, Trend, Ranking | |
| **Last — Email** | SMTP delivery for Critical only | Infra stub exists from V2; wire channel last |

---

## Metric Store contract (hard rules)

```
scope       -> 'server' | 'job' | 'session' | 'database'
scope_id    -> id for that scope
metric_name -> controlled vocabulary (duration_sec, blocking_wait_ms, failed, ...)
dims        -> small JSON only for essential dims (e.g. {"step":"2"})
value       -> number
ts          -> timestamp
```

- Never put high-cardinality open fields in `dims` (full SQL text, full error message, duplicate SessionId).
- Soft daily row-count ceiling + monitor query from day one.
- Reject exploding dimensions at design time; do not “add now, clean later”.

---

## Known V1 / early Insight limitations (honest scope)

### 1) Snapshot ≠ Event

- V1/V2 Insight blocking means: **blocking active at snapshot time**, not every blocking episode that ever occurred.
- Sensitive metrics (blocking) may sample more often (e.g. 1 min vs 5 min). This reduces misses; it does **not** guarantee 100% capture — say so in UI copy.
- **Frequently Blocking** (V2.5) = count of snapshots where blocking was seen — **not** count of real episodes. Label/tooltip must say which.

### 2) Cardinality

See contract above. Soft daily ceiling required.

### 3) False positive = trust death

- Early rules: only unambiguous bad (Job Failed; Blocking with conservative wait threshold).
- Severity: Info / Warning / Critical — **only Critical** may email (when email ships).
- Cooldown: per-rule **and** per-target (one digest “failed 5 times”, not 5 emails).
- Feedback: “این مهم نبود” on each Insight for threshold tuning.

### 4) No duplication with Live Monitor

- Live = direct DMV reads (current app path).
- Insights = aggregated Metric Store only.
- Insight UI: sentence + link “مشاهده جزئیات در Activity Monitor” — no SessionId/Login/Host detail grids.

---

## Email (last phase, early stub)

- Implement a notifier interface + no-op / log backend early so Insights can emit events.
- Do not block V2 on SMTP.
- When enabled: Critical only + cooldown + per-target digest.
