# Object Intelligence Nav Unify — Deferred

**Date:** 2026-08-08  
**Status:** Explicitly deferred  
**Depends on:** Tables & Growth history in production use; Disk module (optional)

---

## Decision

Do **not** merge Indexes + Tables + Disk into one schema or one mega-module now.

When product wants a single brand entry later:

- Add a shell / Home entry that deep-links existing modules  
- Reuse data already in `insight.IdxCat_*`, `insight.ObjSize_History`, and future file snapshots  
- **No** re-collection path; **no** schema merge  

Until then:

- **Indexes** = Object Intelligence (index triage) — ready  
- **Tables & Growth** = independent — ready (this ship)  
- **Disk & DB Health** = soon (see `2026-08-08-disk-db-health-design.md`)  
