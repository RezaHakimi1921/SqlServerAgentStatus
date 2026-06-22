import os
import pyodbc
from dotenv import load_dotenv

load_dotenv()

# Fallback values used if .env is missing
_SERVER   = os.getenv("SQL_SERVER",   "192.168.210.131")
_DATABASE = os.getenv("SQL_DATABASE", "msdb")
_USER     = os.getenv("SQL_USER",     "__REDACTED__")
_PASSWORD = os.getenv("SQL_PASSWORD", "__REDACTED__")
_TIMEOUT  = int(os.getenv("SQL_TIMEOUT", "10"))

CONN_STR = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    f"SERVER={_SERVER};"
    f"DATABASE={_DATABASE};"
    f"UID={_USER};"
    f"PWD={_PASSWORD};"
    "TrustServerCertificate=yes;"
    "Encrypt=no;"
    f"Connection Timeout={_TIMEOUT};"
)

def get_connection():
    return pyodbc.connect(CONN_STR, timeout=_TIMEOUT)

def rows_to_dicts(cursor):
    cols = [c[0] for c in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]

def get_all_data():
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                CONVERT(VARCHAR(36), ja.job_id) AS job_id,
                j.name,
                ja.start_execution_date AS start_dt
            FROM msdb.dbo.sysjobactivity ja
            JOIN msdb.dbo.sysjobs j ON j.job_id = ja.job_id
            WHERE ja.session_id = (
                SELECT MAX(session_id) FROM msdb.dbo.sysjobactivity
            )
            AND ja.start_execution_date IS NOT NULL
            AND ja.stop_execution_date IS NULL
        """)
        running = rows_to_dicts(cur)

        cur.execute("""
            WITH all_hist AS (
                SELECT
                    CONVERT(VARCHAR(36), jh.job_id) AS job_id,
                    j.name,
                    jh.step_id,
                    jh.step_name,
                    jh.run_date,
                    jh.run_time,
                    jh.run_duration,
                    jh.run_status,
                    jh.message,
                    ROW_NUMBER() OVER (
                        PARTITION BY jh.job_id,
                            CASE WHEN jh.step_id = 0 THEN 0 ELSE 1 END
                        ORDER BY jh.run_date DESC, jh.run_time DESC
                    ) AS rn
                FROM msdb.dbo.sysjobhistory jh
                JOIN msdb.dbo.sysjobs j ON j.job_id = jh.job_id
            ),
            has_summary AS (
                SELECT DISTINCT job_id FROM all_hist WHERE step_id = 0
            )
            SELECT job_id, name, step_id, step_name,
                   run_date, run_time, run_duration, run_status, message
            FROM all_hist h
            WHERE rn <= 50
              AND (
                (h.step_id = 0)
                OR (h.step_id > 0 AND h.job_id NOT IN (SELECT job_id FROM has_summary))
              )
            ORDER BY run_date DESC, run_time DESC
        """)
        history_raw = rows_to_dicts(cur)
        return running, history_raw
    finally:
        conn.close()

def get_step_history(job_id: str):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT TOP 200
                jh.step_id,
                jh.step_name,
                jh.run_date,
                jh.run_time,
                jh.run_duration,
                jh.run_status,
                jh.message
            FROM msdb.dbo.sysjobhistory jh
            WHERE CONVERT(VARCHAR(36), jh.job_id) = ?
              AND jh.step_id > 0
            ORDER BY jh.run_date DESC, jh.run_time DESC
        """, job_id)
        return rows_to_dicts(cur)
    finally:
        conn.close()
