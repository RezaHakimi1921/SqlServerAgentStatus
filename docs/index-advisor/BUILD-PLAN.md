# Index Advisor — برنامه ساخت (v1)

> Practical build/run plan for DBA + app.
> برنامه عملی ساخت و اجرای Index Advisor — نسخه ۱.
> Mirrors: `D:\Uni-Project\docs\index-advisor\BUILD-PLAN.md` ↔ `E:\SqlserverAgentProject\SqlServerAgentStatus\docs\index-advisor\BUILD-PLAN.md`
>
> **App/UI design (v1):** `docs/superpowers/specs/2026-08-16-index-module-v1-design.md`  
> (`INDEX_MODULE_DESIGN.md` is superseded for implementation.)

---

## تصمیم‌های قفل‌شده / Locked decisions

| # | فارسی | English |
|---|--------|---------|
| 1 | **فقط خواندنی**؛ خروجی T-SQL تولید می‌شود، **هرگز** روی DB مشتری اجرا نمی‌شود | **Read-only**; generate T-SQL only — **never** execute against customer DBs |
| 2 | در v1 **بدون** Consolidation / Super Index | **No** Consolidation / Super Index in v1 |
| 3 | مدل داده: **Snapshot + Delta** (دلتا در API محاسبه می‌شود) | Data model: **Snapshot + Delta** (delta computed in API) |
| 4 | Confidence **0–100** + reasons؛ اسکریپت قابل کپی فقط اگر **score ≥ 70** | Confidence **0–100** + reasons; copyable script only if **score ≥ 70** |
| 5 | AG/Replica از روز اول (`ObservedReplicaRole`) | AG/Replica from day one (`ObservedReplicaRole`) |
| 6 | DB هدف: **SmartMonitorDB**، schema **`insight` / `Insight`** — **CREATE DATABASE نکن** | Target DB: **SmartMonitorDB**, schema **`insight`/`Insight`** — **do not CREATE DATABASE** |
| 7 | Fingerprint MissingIndex قطعی (deterministic) — جزئیات در FINGERPRINT.md | MissingIndex fingerprint is **deterministic** — see FINGERPRINT.md |

---

## فازها / Phases

### فاز 0 — Schema (انجام‌شده اگر جداول ساختی)

**Phase 0 — Schema (done if tables already exist)**

| | |
|--|--|
| فایل / File (product) | `scripts/sql/SqlMonitor_IndexAdvisor_Phase0.sql` |
| Mirror (docs) | `docs/index-advisor/01-Insight-IndexAdvisor-Phase0.sql` |
| جداول / Tables | `ServerTarget`, `CollectionBatch`, `CollectionRun`, `IndexSnapshot`, `MissingIndexSnapshot` |
| Seed | حداقل یک ردیف `ServerTarget` با `IsActive = 1` |
| Gap-fix | `CollectionRun.Status` باید `Running` را هم بپذیرد (Capture اول Running می‌نویسد) |

اگر جداول از قبل در `SmartMonitorDB` هستند، این فایل را دوباره اجرا نکنید مگر برای gap-check.
Skip re-run if tables already exist; only use for gap-check / fresh lab.

---

### فاز 1 — Capture Index usage (**الان بساز / build now**)

**Phase 1 — Index usage capture**

| Object | File (product repo) |
|--------|---------------------|
| SP `insight.USP_IndexAdvisor_Capture` | `scripts/sql/SqlMonitor_IndexAdvisor_Capture.sql` |
| SQL Agent jobs | `scripts/sql/SqlMonitor_IndexAdvisor_Jobs.sql` |

**Jobs**

| Job | Schedule | Purpose |
|-----|----------|---------|
| `SqlMonitor_IndexAdvisor_HourlyCapture` | Hourly | Continuous usage snapshots |
| `SqlMonitor_IndexAdvisor_PreRebuild` | Nightly **23:30** | Snapshot before overnight rebuild window (~01:00) |

**Behavior (Phase 1)**

- Inserts `CollectionBatch` + `CollectionRun` + `IndexSnapshot`
- Fast path: `dm_db_partition_stats` — **`FragmentationPercent` = NULL** for now
- Scans online user DBs the instance can access
- Records AG role when present (`ObservedReplicaRole`: Primary / Secondary / Standalone)
- **MissingIndex insert is NOT in this SP yet** → Phase 2

**Does not**

- Create databases or run DDL on customer/user DBs
- Depend on Python or Windows Task Scheduler

---

### فاز 2 — Missing Index capture

**Phase 2 — Missing Index**

- Populate `MissingIndexSnapshot` with deterministic **Fingerprint** (see `FINGERPRINT.md`)
- Still need separate script(s) — track as TODO:

**TODO (Phase 2)**

- [ ] SP or batch: read `sys.dm_db_missing_index_*` per target DB
- [ ] Normalize eq / ineq / included columns per FINGERPRINT.md
- [ ] Compute `Fingerprint` = SHA256 hex of canonical string
- [ ] INSERT into `insight.MissingIndexSnapshot` keyed by run + fingerprint
- [ ] Optional: Agent schedule (hourly with Capture, or separate job)
- [ ] App: surface missing-index recommendations with confidence ≥ 70 gate
- [ ] Docs: extend INSTALL-CHECKLIST with Phase 2 verify SELECTs

---

### فاز 3 — UI (اپ SmartMonitor)

**Phase 3 — SmartMonitor app UI**

- Overview fed from `advisor_snapshot` (when available)
- Triage list with **confidence** + reasons
- **No** consolidation UI / Super Index in v1
- Copy T-SQL only when confidence **≥ 70**; otherwise show why score is low

---

## ترتیب اجرا برای تو (DBA) / Run order

روی **همان SQL Server** اجرا کنید (نه Task ویندوز لپ‌تاپ).
Run on the **SQL Server** itself (not a laptop Windows Task).

1. **اگر جداول نیست (یا gap-check)** → اجرا کن `scripts/sql/SqlMonitor_IndexAdvisor_Phase0.sql` روی `SmartMonitorDB`
2. **چک `ServerTarget`** → حداقل یک `IsActive = 1`
3. اجرا کن **`SqlMonitor_IndexAdvisor_Capture.sql`** (CREATE OR ALTER proc)
4. اجرا کن **`SqlMonitor_IndexAdvisor_Jobs.sql`** (Hourly + PreRebuild)
5. **`EXEC insight.USP_IndexAdvisor_Capture;`** دستی + verify SELECTs (پایین)
6. **حذف Task ویندوز** اگر هنوز هست (لپ‌تاپ خاموش = Capture قطع می‌شود)

```bat
schtasks /Delete /TN "SqlMonitor_IndexAdvisor_Hourly" /F
```

هم‌تراز نصب: `INSTALL-SQL-AGENT.md` و `INSTALL-CHECKLIST.md`.

---

## دسترسی‌ها / Permissions

| نقش / Role | حداقل دسترسی / Minimum |
|------------|-------------------------|
| Capture / Agent job login | `INSERT`/`UPDATE` on `insight.*`, `VIEW SERVER STATE`, access to user DBs being scanned |
| App (read) | `SELECT` on `CollectionBatch`, `CollectionRun`, `IndexSnapshot` (+ Missing later) |
| Installer (one-time) | Usually **sysadmin** (CREATE PROCEDURE + SQL Agent jobs in `msdb`) |

---

## فایل‌های مرجع / Reference files (full paths)

### Uni-Project (docs mirror)

| File | Path |
|------|------|
| Phase 0 DDL | `D:\Uni-Project\docs\index-advisor\01-Insight-IndexAdvisor-Phase0.sql` |
| Capture SP | `D:\Uni-Project\docs\index-advisor\SqlMonitor_IndexAdvisor_Capture.sql` |
| Jobs | `D:\Uni-Project\docs\index-advisor\SqlMonitor_IndexAdvisor_Jobs.sql` |
| Fingerprint | `D:\Uni-Project\docs\index-advisor\FINGERPRINT.md` |
| Install Agent | `D:\Uni-Project\docs\index-advisor\INSTALL-SQL-AGENT.md` |
| Checklist | `D:\Uni-Project\docs\index-advisor\INSTALL-CHECKLIST.md` |
| This plan | `D:\Uni-Project\docs\index-advisor\BUILD-PLAN.md` |

### SmartMonitor product repo (source of truth for runnable SQL)

| File | Path |
|------|------|
| Phase 0 DDL | `E:\SqlserverAgentProject\SqlServerAgentStatus\scripts\sql\SqlMonitor_IndexAdvisor_Phase0.sql` |
| Capture SP | `E:\SqlserverAgentProject\SqlServerAgentStatus\scripts\sql\SqlMonitor_IndexAdvisor_Capture.sql` |
| Jobs | `E:\SqlserverAgentProject\SqlServerAgentStatus\scripts\sql\SqlMonitor_IndexAdvisor_Jobs.sql` |
| Docs folder | `E:\SqlserverAgentProject\SqlServerAgentStatus\docs\index-advisor\` |
| Phase 0 (docs mirror) | `E:\SqlserverAgentProject\SqlServerAgentStatus\docs\index-advisor\01-Insight-IndexAdvisor-Phase0.sql` |

> برای نصب روی سرور، ترجیحاً از **`scripts/sql/*.sql`** در ریپوی SmartMonitor استفاده کنید.
> Prefer product `scripts/sql/*.sql` when deploying to the server.

---

## Verify SQL block

بعد از Phase 0 + Capture + Jobs / After Phase 0 + Capture + Jobs:

```sql
USE SmartMonitorDB;
GO

SELECT TargetId, ServerName, IsActive
FROM insight.ServerTarget;

EXEC insight.USP_IndexAdvisor_Capture;

SELECT TOP 5 *
FROM insight.CollectionBatch
ORDER BY StartedAtUtc DESC;

SELECT TOP 10
    RunId, BatchId, TargetId, CollectedAtUtc,
    UptimeHours, ObservedReplicaRole, Status
FROM insight.CollectionRun
ORDER BY CollectedAtUtc DESC;

SELECT COUNT(*) AS IndexSnapshotRows
FROM insight.IndexSnapshot;

SELECT name, enabled
FROM msdb.dbo.sysjobs
WHERE name LIKE N'SqlMonitor_IndexAdvisor%';
```

**Expected:** batch `Status` completes (not stuck Running), `IndexSnapshot` count grows, both jobs exist and `enabled = 1`.

---

## خلاصه وضعیت v1 / v1 status snapshot

| Phase | Status | Notes |
|-------|--------|-------|
| 0 Schema | Ready (`scripts/sql` + docs mirror) | `insight` schema; Running status gap-fix |
| 1 Capture + Jobs | Ready to deploy | Frag = NULL; no MissingIndex yet |
| 2 Missing Index | Planned | Fingerprint + separate capture TODO |
| 3 App UI | Planned | Overview + triage; confidence gate; no consolidation |

---

*Last aligned: Phase 0 hardened into `scripts/sql` (insight schema, Running CHECK gap-fix); Capture/Jobs headers synced.*
