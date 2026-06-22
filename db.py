import pyodbc
from datetime import datetime

CONN_STR = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=192.168.210.131;"
    "DATABASE=msdb;"
    "UID=__REDACTED__;"
    "PWD=__REDACTED__;"
    "TrustServerCertificate=yes;"
    "Encrypt=no;"
    "Connection Timeout=5;"
)

STATUS_LABELS = {0: "Failed", 1: "Succeeded", 2: "Retry", 3: "Canceled"}


def get_connection():
    return pyodbc.connect(CONN_STR, timeout=5)


def rows_to_dicts(cursor):
    cols = [c[0] for c in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def test_connection():
    try:
        conn = get_connection()
        conn.close()
        return True
    except Exception as e:
        print(f"Connection failed: {e}")
        return False


def parse_duration_seconds(run_duration: int) -> int:
    h = run_duration // 10000
    m = (run_duration % 10000) // 100
    s = run_duration % 100
    return h * 3600 + m * 60 + s


def parse_run_datetime(run_date: int, run_time: int) -> datetime:
    ds = str(run_date)
    ts = str(run_time).zfill(6)
    return datetime(int(ds[:4]), int(ds[4:6]), int(ds[6:]),
                    int(ts[:2]), int(ts[2:4]), int(ts[4:]))


def get_all_jobs():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT CONVERT(VARCHAR(36), j.job_id) AS job_id, j.name, j.enabled
        FROM msdb.dbo.sysjobs j
        ORDER BY j.name
    """)
    rows = rows_to_dicts(cursor)
    conn.close()
    return rows


def get_running_jobs():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT CONVERT(VARCHAR(36), ja.job_id) AS job_id, j.name,
               ja.start_execution_date, ja.last_executed_step_id
        FROM msdb.dbo.sysjobactivity ja
        JOIN msdb.dbo.sysjobs j ON j.job_id = ja.job_id
        WHERE ja.session_id = (SELECT MAX(session_id) FROM msdb.dbo.sysjobactivity)
          AND ja.start_execution_date IS NOT NULL
          AND ja.stop_execution_date IS NULL
    """)
    rows = rows_to_dicts(cursor)
    conn.close()
    return rows


def get_job_history():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT TOP 2000
               CONVERT(VARCHAR(36), jh.job_id) AS job_id, j.name,
               jh.step_id, jh.step_name, jh.run_date, jh.run_time,
               jh.run_duration, jh.run_status, jh.message
        FROM msdb.dbo.sysjobhistory jh
        JOIN msdb.dbo.sysjobs j ON j.job_id = jh.job_id
        WHERE jh.step_id = 0
        ORDER BY jh.run_date DESC, jh.run_time DESC
    """)
    rows = rows_to_dicts(cursor)
    conn.close()
    for r in rows:
        r["start_dt"] = parse_run_datetime(r["run_date"], r["run_time"])
        r["duration_seconds"] = parse_duration_seconds(r["run_duration"])
        r["status_label"] = STATUS_LABELS.get(r["run_status"], "Unknown")
    return rows


def get_step_history(job_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT TOP 500
               jh.step_id, jh.step_name, jh.run_date, jh.run_time,
               jh.run_duration, jh.run_status, jh.message
        FROM msdb.dbo.sysjobhistory jh
        WHERE CONVERT(VARCHAR(36), jh.job_id) = ? AND jh.step_id > 0
        ORDER BY jh.run_date DESC, jh.run_time DESC
    """, (job_id,))
    rows = rows_to_dicts(cursor)
    conn.close()
    for r in rows:
        r["start_dt"] = parse_run_datetime(r["run_date"], r["run_time"])
        r["duration_seconds"] = parse_duration_seconds(r["run_duration"])
        r["status_label"] = STATUS_LABELS.get(r["run_status"], "Unknown")
    return rows


if __name__ == "__main__":
    print("Connected:", test_connection())
