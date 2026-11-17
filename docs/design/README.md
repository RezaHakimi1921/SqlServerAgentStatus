# Design sources — SmartMonitor / SQL Agent

## Canonical Figma Make export (Manus)

Unpacked from `SQL Server Agent Status Dashboard.zip` into:

- [`figma-make/`](./figma-make/) — React + Vite + Tailwind v4 UI (source of visual truth)
  - `src/App.tsx` — shell, dashboard, jobs table, settings drawer, incidents
  - `src/FleetView.tsx` — multi-server fleet
  - `src/TimelineView.tsx` — timeline / calendar-style view
  - `src/index.css` — tokens + component CSS (`--green`, `--navy`, `.sidebar`, `.stat-card`, …)

## Manus product docs

Extracted from `.tmp/reference-docs.txt`:

| File | Content |
|------|---------|
| [`manus-docs/01-سند_قابلیتها.md`](./manus-docs/01-سند_قابلیتها.md) | Capability roadmap |
| [`manus-docs/02-سند_نیازمندی_از_سمت_مانوس.md`](./manus-docs/02-سند_نیازمندی_از_سمت_مانوس.md) | Requirements from Manus |
| [`manus-docs/03-SQL_Server_Agent_Monitor.md`](./manus-docs/03-SQL_Server_Agent_Monitor.md) | EN product brief |
| [`manus-docs/04-مانیتور_SQL_Server_Agent.md`](./manus-docs/04-مانیتور_SQL_Server_Agent.md) | FA product brief |

## Port target

Product runtime remains **Dash** (`app.py` + `modules/*` + `assets/custom.css`).  
Figma Make is the **pixel/IA reference**; we port shell + screens into Dash CSS/layouts — we do not replace the backend with the React scaffold.

### Figma nav → Dash modules (v1 port map)

Source: `figma-make/src/App.tsx` (`activeNav`) + Fleet/Timeline views.

| Figma key | FA label | Dash target |
|-----------|----------|-------------|
| `overview` | نمای کلی | `home` (greeting, freshness, KPIs snippet, module tiles) |
| `jobs` | جاب‌ها | `jobs` (stat cards + workspace table + filters) |
| `timeline` | خط زمانی | Jobs Gantt / `TimelineView` chrome (then wire real gantt data) |
| `health` | مدیریت سرورها | `FleetView` chrome → multi-instance later; Settings connections now |
| `incidents` | رخدادها | `insights` (+ Activity blocking as deep link) |
| `history` | تاریخچه و روند | Jobs history / trends (no dedicated Figma screen yet) |
| settings footer | تنظیمات سامانه | `settings` |
| (product extras) | — | `activity`, `tables`, `indexes`, `docs` remain in rail |

**Tokens locked in `assets/custom.css` `:root` (light Figma, not old OLED):**  
`--green #0c7c59`, `--navy #14231e`, `--bg-primary #f4f7f5`, `--sidebar 254px`, Vazirmatn, RTL right rail.  

**CSS load order:** `custom.css` → `figma-dash-bridge.css` → `figma-theme.css` → **`zz-figma-force.css`** (wins last).  

**Toast:** product rule stays **top-right** (account for rail).

**CSS classes for fidelity:** `app-shell`, `sidebar`/`side-nav`, `brand-mark`, `topbar`/`live-pill`, `stat-card`, `freshness-banner`, `workspace-card`/`status-badge`, `fleet-server`, `gantt-shell`/`gantt-run`, `button.primary|secondary`.

### Figma fidelity skill

Project skill: `.cursor/skills/figma-fidelity/SKILL.md`  
Source of truth: live Make via MCP (`docs/design/figma-make-live/`) + zip (`docs/design/figma-make/`).  
Note: Make files do not support `create_session` / `get_screenshot`; use `get_design_context` + resource fetch (and exported PNGs under `figma-make-live/ref/`).

### Implementation slices

0. Tokens + light canvas + dark green sidebar — **done** (`assets/figma-theme.css`, `figma-dash-bridge.css`, `modules/shell/rail.py`)
1. Topbar + greeting + freshness — **done** (`app.py` topbar, `modules/home/layout.py`)
2. Overview Home = Make layout (heading, freshness, KPI grid, jobs preview, incidents + servers lower-grid) — **done** (chrome; live KPI numbers wire next)
3. Jobs page heading + i18n filters + inline refresh chrome — **done**; table row/server column fidelity — **next**
4. Timeline / Gantt chrome — **partial** (`gantt-shell` wrapper; data wiring = next module pass)
5. Fleet chrome (`FleetView`) — **pending** (module pass: health / multi-server)
6. Incidents / Insights restyle — **pending** (module pass; Home lower-grid is Make chrome)
7. Activity / Tables / Indexes / Docs / Settings polish — **tokens applied**; deep layout = module passes

### Module-by-module order (feature + fidelity)

1. **Jobs** — table columns vs Make (server/last run), next-run from schedules, Gantt, retry status
2. **Activity** — Blocking / Session Lookup on light chrome
3. **Insights / Incidents** — replace Home chrome with live data + deep links
4. **Tables** then **Indexes**
5. **Settings / Fleet** — connections + health
6. **Docs** last
