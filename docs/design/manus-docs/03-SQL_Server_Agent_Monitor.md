# SQL Server Agent Monitor

A lightweight web dashboard to monitor **SQL Server Agent Jobs** — running jobs, completed runs, Gantt timeline, and step-level details.

---

## Quick Start (Windows)

### Prerequisites

See **[INSTALL.md](INSTALL.md)** for full step-by-step setup on a **fresh PC** (Python, ODBC, SQL permissions).

| Component | Required |
|-----------|----------|
| Python 3.9+ (64-bit) | Yes — [python.org](https://www.python.org/downloads/) |
| ODBC Driver 17 or 18 | Yes — [Microsoft download](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server) |
| SQL login (SELECT on `msdb`) | Yes |

> **Common issue:** *"Python was not found… Microsoft Store"* → install Python, disable **App execution aliases** for `python.exe`, then run `setup.bat` again. Details in [INSTALL.md](INSTALL.md).

### Install & Run

```bat
setup.bat    REM install dependencies (first time only)
run.bat      REM starts the app and opens the browser
```

On **first run**, a setup wizard asks for Server, User, and Password. The password is stored in **Windows Credential Manager** (not in `.env`). Server settings are in `.env` (never committed to git).

**Security:** The app binds to `127.0.0.1` by default (local access only). Connection settings can only be changed from the same machine. Gantt and all views use the same read-only SQL connection — credentials never reach the browser.

---

## Features

| Tab | Description |
|-----|-------------|
| ⚡ Running | Live jobs with progress estimate and slow-job detection |
| 📋 All Jobs | Latest run per job, filter by date |
| 📊 Gantt | Timeline of today's job executions |
| 🔍 Details | Step-level history for a selected job |

---

## Configuration

Settings are stored in `.env` (auto-created by the setup wizard):

| Variable | Default | Description |
|----------|---------|-------------|
| `SQL_SERVER` | — | Server name or `HOST\INSTANCE` |
| `SQL_DATABASE` | `msdb` | Database (keep as msdb) |
| `SQL_USER` | — | SQL login |
| *(password)* | — | Stored in Windows Credential Manager |
| `SQL_DRIVER` | `17` | ODBC driver version (17 or 18) |
| `DASH_HOST` | `127.0.0.1` | Bind address (local only by default) |
| `REFRESH_RUNNING` | `15000` | Running jobs refresh (ms) |
| `REFRESH_HISTORY` | `60000` | History refresh (ms) |
| `DASH_PORT` | `8050` | Web UI port |

Use **تغییر اتصال** (Change Connection) in the header to reconfigure.

---

## Tech Stack

- Python · Dash · Plotly · pyodbc

---

---
