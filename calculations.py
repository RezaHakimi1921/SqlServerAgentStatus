import statistics
from datetime import datetime
from collections import defaultdict


def calc_job_stats(history: list) -> dict:
    durations = defaultdict(list)
    for row in history:
        if row["run_status"] == 1:
            durations[row["job_id"]].append(row["duration_seconds"])
    result = {}
    for job_id, durs in durations.items():
        result[job_id] = {
            "avg": statistics.mean(durs),
            "median": statistics.median(durs),
            "stdev": statistics.stdev(durs) if len(durs) > 1 else 0,
            "run_count": len(durs),
        }
    return result


def calc_progress(job_id: str, start_dt: datetime, job_stats: dict) -> dict:
    elapsed = max(0, (datetime.now() - start_dt).total_seconds())
    stat = job_stats.get(job_id)
    if not stat or stat["avg"] == 0:
        return {
            "elapsed": elapsed,
            "avg": None,
            "percent": None,
            "remaining": None,
            "is_slow": False,
            "is_very_slow": False,
        }
    avg = stat["avg"]
    percent = (elapsed / avg) * 100
    return {
        "elapsed": round(elapsed),
        "avg": round(avg),
        "percent": round(percent, 1),
        "remaining": round(max(0, avg - elapsed)),
        "is_slow": percent > 110,
        "is_very_slow": percent > 150,
    }


def fmt_seconds(seconds) -> str:
    if seconds is None:
        return "—"
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sc = divmod(rem, 60)
    if h:
        return f"{h}h {m}m {sc}s"
    if m:
        return f"{m}m {sc}s"
    return f"{sc}s"
