# Index Advisor — Install Checklist / چک‌لیست نصب

Mirror of SmartMonitor:  
`E:\SqlserverAgentProject\SqlServerAgentStatus\docs\index-advisor\INSTALL-CHECKLIST.md`

One clear list for DBA install on **SQL Server** (not the Windows PC).  
یک لیست واضح برای نصب روی **سرور SQL** (نه لپ‌تاپ).

---

## 1. Tables already expected (Phase 0)

Schema: `insight`. Target DB: `SmartMonitorDB`.

| Table | Purpose |
|-------|---------|
| `insight.ServerTarget` | Active scan targets (need ≥1 `IsActive=1`) |
| `insight.CollectionBatch` | One collector wall-clock batch |
| `insight.CollectionRun` | Per-target run + uptime / replica role |
| `insight.IndexSnapshot` | Index usage/size rows per run |
| `insight.MissingIndexSnapshot` | Shell for Phase 2 (empty until Missing capture) |

**DDL (product source of truth):** `scripts/sql/SqlMonitor_IndexAdvisor_Phase0.sql`  
**Docs mirror:** `docs/index-advisor/01-Insight-IndexAdvisor-Phase0.sql`

Re-run Phase0 on existing DBs only for the **Running status gap-fix** (Capture inserts `Running`).

---

## 2. Stored procedure to create (SmartMonitor repo)

| Object | File |
|--------|------|
| `insight.USP_IndexAdvisor_Capture` | `scripts/sql/SqlMonitor_IndexAdvisor_Capture.sql` |

---

## 3. SQL Agent jobs (SmartMonitor repo)

File: `scripts/sql/SqlMonitor_IndexAdvisor_Jobs.sql`

| Job | Schedule |
|-----|----------|
| `SqlMonitor_IndexAdvisor_HourlyCapture` | Hourly |
| `SqlMonitor_IndexAdvisor_PreRebuild` | Nightly 23:30 |

Delete Windows Task if present — laptop off = no capture:

```bat
schtasks /Delete /TN "SqlMonitor_IndexAdvisor_Hourly" /F
```

---

## 4. Optional — ObjSize history

| Object / Job | File (SmartMonitor) |
|--------------|---------------------|
| Capture SP + table | `scripts/sql/SqlMonitor_ObjSizeHistory.sql` |
| Agent job(s) | `scripts/sql/SqlMonitor_ObjSizeHistory_Jobs.sql` |

---

## 5. Verify SELECTs

```sql
SELECT TargetId, ServerName, IsActive FROM insight.ServerTarget;
SELECT TOP 5 * FROM insight.CollectionBatch ORDER BY StartedAtUtc DESC;
SELECT COUNT(*) FROM insight.IndexSnapshot;
SELECT name, enabled FROM msdb.dbo.sysjobs
WHERE name LIKE N'SqlMonitor_IndexAdvisor%';
```

```sql
EXEC insight.USP_IndexAdvisor_Capture;
```

---

## 6. Permissions needed

- Capture/job login: `INSERT`/`UPDATE` on `insight.*`, `VIEW SERVER STATE`, user-DB access  
- App read: `SELECT` on Batch / Run / IndexSnapshot  
- Installer: usually **sysadmin** for proc + Agent jobs  

---

## App v1 rules

- Prefer `advisor_snapshot` when available  
- Confidence 0–100; copyable T-SQL only if **≥ 70**  
- No Consolidation / Super Index; scripts generated only (never executed)
