# Blocking Tree (Live Activity) — Design Spec

**Date:** 2026-08-01  
**Status:** Approved for implementation (pending final user review of this file)  
**Scope:** Live Activity → Blocking tab UI + independent wait-object resolve helper  
**Out of scope:** Metric Store / insight collector `dim` writes (deferred to V1.5; resolve API must stay reusable)

---

## Goal

Replace pairwise “blocker ↔ blocked” cards with a **nested blocking tree** so operators instantly see:

1. Who is the **head blocker** (root)
2. Everyone blocked **directly or indirectly** under that root
3. **Blast radius** (one SPID affecting N sessions)
4. **Chain age** (how long the chain has been alive — not only the last-refresh wait)
5. **SQL snippet** under each node
6. **Readable lock object** (`schema.table`) when resolvable

No new product data model. Same DMV edges; regroup + optional resolve.

---

## Approach

**Chosen:** Python regroup of existing `get_blocking` rows + pure resolve helper (batch lookups).  

**Rejected:** New stored procedure that returns a pre-built tree; Metric Store schema changes in this PR.

---

## 1) Tree construction (from existing pairs)

**Input:** rows from `SqlServerProvider.get_blocking` (fields already present: `blocker_session_id`, `blocked_session_id`, `is_head_blocker`, `wait_*`, SQL/login sides, `request_elapsed_sec`, `wait_resource`, `wait_type`, …).

**Graph rules:**

- Edge: `blocker_session_id → blocked_session_id`
- **Filter self-blocking:** drop edges where `blocker_session_id == blocked_session_id` (parallel threads / same-session noise). Do not build nodes from those edges alone.
- **Cycle guard:** while walking parents/children, track visited SPIDs on the current path. If a cycle is detected (rare pre–deadlock-monitor noise), **break the cycle** and treat the contested node as an **independent root** rather than looping or crashing.
- **Roots:** prefer `is_head_blocker == 1`. Equivalently: a session that blocks others and is not itself blocked by another (after filters). Multiple roots → multiple tree cards.
- **Children:** direct blocked sessions; recurse for indirect victims (nested indentation in UI).
- Deduplicate identical edges before graph build (same key as today’s UI: blocked/blocker/wait_resource/chain_display).

**Output shape (in-memory, not persisted):**

```text
TreeRoot {
  head_session_id
  head_meta…          # login, sql, command, status/age
  blast_radius        # count of distinct sessions under root (victims; optionally include head in “affected” messaging as “1 affecting N”)
  chain_age_sec       # max(request_elapsed_sec) over subtree (see §3)
  children: [TreeNode…]
}
TreeNode {
  session_id, login, sql_snippet, wait_sec, wait_type,
  wait_resource_raw, wait_object,   # wait_object = resolve result or None
  children: […]
}
```

---

## 2) Blast radius

**Per root (primary):** “1 session (`{spid}`) affecting **N** sessions” where N = distinct blocked descendants under that root.

**Page summary / health strip:**

| Card | Meaning |
|------|---------|
| **Blast radius** | Count of **distinct blocked SPIDs across all roots** (dedupe the SPID set globally before the final number — a session must not inflate the strip if it briefly appears under two roots in a racy snapshot) |
| **Head blockers** | Count of roots |
| **Chain age** | Max `chain_age_sec` across roots (formatted) |

**Per-root blast** still shows “1 affecting N” for that tree’s descendants only. The strip total uses the **union** of blocked SPIDs, not a naive sum of per-root N.

Replace or demote the old “Longest Wait” strip emphasis so chain age is first-class (mock: Blast / Heads / Chain age).

---

## 3) Chain age

- Per root: `chain_age_sec = max(request_elapsed_sec)` over the head and all descendants that have a value; if only wait ms is available for a node, do not substitute wait for chain age.
- Display with existing duration helpers (`fmt_running_label` / `HH:MM:SS`), not WhoIsActive day+ms.
- Instantaneous `wait_time` remains on **blocked** nodes as “wait” (e.g. `1.7s wait`); head shows running/age style (e.g. `running 2m 40s`).

---

## 4) SQL under each node

- Show a one-line truncated snippet from `blocker_sql` / `blocked_sql` (existing LEFT 2000 text).
- Keep existing modal “view SQL” control for full text.
- Do not require Session Lookup to understand why the lock exists.

---

## 5) Wait object resolve (independent helper)

### API (must stay V1.5-ready)

```text
resolve_wait_object(wait_resource: str, wait_type: str | None) -> str | None
```

- **Success:** `"schema.table"` only (no Persian, no decorative formatting).
- **Failure / unknown / exception:** **`None`** — never return raw `wait_resource` from this function (raw must not become a Metric Store `dim` later).
- **No Dash / layout / request context** dependencies. Callable from Live UI batch path and later from collectors.

### Parsing (per lock resource shape)

| Prefix / shape | Strategy |
|----------------|----------|
| `OBJECT: dbid:objid…` | `OBJECT_SCHEMA_NAME` / `OBJECT_NAME` with **database_id** (3-arg / db-scoped forms) |
| `KEY: dbid:hobtid …` | Map `hobt_id` → object via `sys.partitions` (then schema.table in that db) |
| `PAGE:` / `RID:` | Best-effort via page → object when practical; else `None` |
| Unknown | `None` |

`wait_type` (e.g. `LCK_M_*`) may hint lock-family parsing but **resource string prefix is authoritative**.

### Batching (mandatory — avoid N+1)

- Before resolve, collect unique `(wait_resource, wait_type)` (or unique `wait_resource` if type unused for keying) across **all nodes in the payload**.
- **Group unique keys by `db_id`** extracted from the resource string. `OBJECT_NAME(..., database_id)` and `sys.partitions` lookups are **database-scoped**; a single global batched query across mixed DBs is incorrect.
- For each `db_id` group, run **one batched lookup** (not one round-trip per node). Number of SQL round-trips ≈ number of distinct databases in the snapshot, not number of nodes.
- Map results back onto nodes.

### Error handling

- Entire resolve path wrapped so **any SQL/exception** → log + `None` for that key.
- A failed resolve **must not** fail the Live Blocking request; UI still renders the tree.
- UI fallback when `wait_object is None`: show a **humanized raw** string (option B) in the card only — formatting lives in the UI layer, not in `resolve_wait_object`.

### Placement

- Suggested: `core/wait_resource.py` (or similar) + thin SQL helpers used only by that module / provider.
- Live `get_blocking` may attach `wait_object` after fetch via the batch map; do not inline unresolved OBJECT_NAME-only logic solely inside the recursive CTE UI query.

---

## 6) Collapse UI

- Under each root, show a small number of child nodes by default (e.g. **2** visible, matching mock).
- Pill: `+ N session دیگر under this root` expands/collapses the rest.
- Avoid infinite scroll of duplicate pair cards.

---

## 7) Visual / interaction notes

- One card per root; nested rows with tree rail (indent + connector).
- Head: red/critical badge + “head blocker”; victims: warning-tone badges + wait on the right.
- Blast radius summary tile uses critical emphasis when N > 0.

---

## Explicit non-goals (this PR)

- Persisting resolved `schema.table` into insight Metric Store / changing collector dims
- Deadlock graph product (beyond cycle-safe tree build)
- Changing Running Now or Session Lookup layouts

---

## Acceptance checklist

- [ ] Blocking tab shows trees (roots + nested victims), not only pair cards
- [ ] Blast radius and chain age visible at strip and/or per root; strip blast = **global deduped** blocked SPID set
- [ ] SQL snippet visible per node without Session Lookup
- [ ] Unique wait resources resolved at most once per refresh; lookups **batched per `db_id`** (not one global cross-db query, not per-node)
- [ ] Self-edges filtered; cycles do not hang or crash
- [ ] `resolve_wait_object` returns only `schema.table` or `None`; exceptions → `None`
- [ ] UI shows humanized raw resource when resolve is `None`
- [ ] No Metric Store schema/collector writes in this PR
- [ ] Helper importable without Dash

---

## Follow-up (V1.5)

- Insight collector calls the same `resolve_wait_object` (batch) and stores only non-null `schema.table` as a constrained `dim` for “frequently blocking per table”.
