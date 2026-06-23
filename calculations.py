from datetime import datetime, timedelta

def parse_run_duration(run_duration):
    h = run_duration // 10000
    m = (run_duration % 10000) // 100
    s = run_duration % 100
    return h * 3600 + m * 60 + s

def parse_run_datetime(run_date, run_time):
    try:
        date_str = str(run_date).zfill(8)
        time_str = str(run_time).zfill(6)
        return datetime.strptime(date_str + time_str, "%Y%m%d%H%M%S")
    except Exception:
        return None

def fmt_seconds(seconds):
    if seconds is None:
        return "-"
    h = int(seconds) // 3600
    m = (int(seconds) % 3600) // 60
    s = int(seconds) % 60
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"

def enrich_history(history_raw):
    """Add start_dt, duration_seconds, end_dt to each history row."""
    enriched = []
    for h in history_raw:
        row = dict(h)
        dt = parse_run_datetime(h["run_date"], h["run_time"])
        dur = parse_run_duration(h["run_duration"])
        row["start_dt"] = dt
        row["duration_seconds"] = dur
        row["end_dt"] = (dt + timedelta(seconds=dur)) if dt else None
        enriched.append(row)
    return enriched

def calc_job_stats(history):
    """Per-job average duration from successful runs."""
    stats = {}
    for h in history:
        if h["run_status"] != 1:
            continue
        jid = h["job_id"]
        dur = h["duration_seconds"]
        if jid not in stats:
            stats[jid] = {"total": 0, "count": 0}
        stats[jid]["total"] += dur
        stats[jid]["count"] += 1
    return {jid: v["total"] / v["count"] for jid, v in stats.items() if v["count"] > 0}

def calc_progress(job_id, start_dt, job_stats):
    if start_dt is None:
        return None, None, False, False
    elapsed = (datetime.now() - start_dt).total_seconds()
    avg = job_stats.get(job_id)
    if not avg:
        return None, None, False, False
    pct = min(int(elapsed / avg * 100), 99)
    remaining = max(0, avg - elapsed)
    is_slow = elapsed > avg * 1.1
    is_very_slow = elapsed > avg * 1.5
    return pct, remaining, is_slow, is_very_slow
