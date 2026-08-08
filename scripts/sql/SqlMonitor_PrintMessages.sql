/*
  SqlMonitor_PrintMessages — capture PRINT / low-severity messages for Session Lookup.

  Run as sysadmin (or a login with ALTER ANY EVENT SESSION).
  Replace [AgentGraph] with your monitor login from app Settings (SQL_USER).
*/

-- ─────────────────────────────────────────────────────────────
-- 1) Permissions for the monitor login (SERVER-level)
-- ─────────────────────────────────────────────────────────────
GRANT VIEW SERVER STATE TO [AgentGraph];
GRANT VIEW ANY DEFINITION TO [AgentGraph];
-- Needed so AgentGraph can read the XE ring buffer targets:
GRANT ALTER ANY EVENT SESSION TO [AgentGraph];
GO

-- ─────────────────────────────────────────────────────────────
-- 2) Create / replace the Extended Events session
-- ─────────────────────────────────────────────────────────────
IF EXISTS (SELECT 1 FROM sys.server_event_sessions WHERE name = N'SqlMonitor_PrintMessages')
BEGIN
    ALTER EVENT SESSION SqlMonitor_PrintMessages ON SERVER STATE = STOP;
    DROP EVENT SESSION SqlMonitor_PrintMessages ON SERVER;
END
GO

CREATE EVENT SESSION SqlMonitor_PrintMessages ON SERVER
ADD EVENT sqlserver.error_reported (
    ACTION (
        sqlserver.session_id,
        sqlserver.client_app_name,
        sqlserver.username,
        sqlserver.sql_text
    )
    WHERE (
        [severity] <= 10          -- PRINT / info / low severity (not real errors)
        AND [sqlserver].[is_system] = 0
    )
)
ADD TARGET package0.ring_buffer (SET max_memory = 8192)
WITH (
    MAX_MEMORY = 4096 KB,
    EVENT_RETENTION_MODE = ALLOW_SINGLE_EVENT_LOSS,
    MAX_DISPATCH_LATENCY = 5 SECONDS,
    STARTUP_STATE = ON
);
GO

ALTER EVENT SESSION SqlMonitor_PrintMessages ON SERVER STATE = START;
GO

-- ─────────────────────────────────────────────────────────────
-- 3) Verify
-- ─────────────────────────────────────────────────────────────
SELECT s.name, s.total_buffer_size, t.target_name
FROM sys.dm_xe_sessions s
JOIN sys.dm_xe_session_targets t ON t.event_session_address = s.address
WHERE s.name = N'SqlMonitor_PrintMessages';

-- Optional smoke test (in another window), then Lookup that SPID:
-- PRINT 'FACTURE: Updated 10000 rows';
