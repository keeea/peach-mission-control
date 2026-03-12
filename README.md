# Peach Mission Control (V3)

Mission-control dashboard for Lan + Peach collaboration, upgraded into a **single-filter navigation system** across Dashboard, Kanban, and Reports. The redesign shifts the product from a page-by-page collection of widgets into a balanced operating surface: execution efficiency + management visibility.

## What changed in V3

### 1) Information architecture redesign

The product now follows a shared operating rhythm inspired by modern YouTube-style dashboard pacing: quick summary first, then action queue, then risk escalation, then timeline + insights.

- **Dashboard** now uses four layers:
  - **Top summary**
  - **Action center**
  - **Risk & blockers**
  - **Timeline / insights**
- **Kanban** is now a scoped execution view, not a separate filtering system.
- **Reports** now reads from the same filter language and presents weekly throughput / blockers / change timeline.

### 2) Unified filter design

The app no longer assumes a default project perspective. Instead, all key pages share the same filter language and URL query params:

- `q`
- `project`
- `status`
- `owner`
- `priority`

Examples:

- `/` → full operating view
- `/?project=portfolio&owner=lan`
- `/kanban?project=portfolio&priority=high`
- `/reports/weekly?project=portfolio&status=blocked`
- `/api/tasks?owner=peach&priority=medium`

### 3) Backend + frontend filter linkage

Filters are now wired through:

- **query params**
- **page filter forms**
- **backend SQL filtering**
- **API response payloads**
- **cross-page navigation links that preserve current scope**
- **filtered exports and filtered weekly reports**

This means Dashboard, Kanban, Reports, `/api/tasks`, export endpoints, and `/api/reports/weekly` all speak the same filtering language.

---

## Removed modules and why

These were removed from the dashboard surface because they were low-value, duplicative, or distracted from the main operating loop:

1. **Application Pipeline card**
   - Reason: it mixed a different domain into the main operating cockpit and diluted decision focus.
   - The job application model still exists in code, but it is no longer promoted in the core dashboard.

2. **Add Project / Add Job Application forms on the homepage**
   - Reason: three creation forms at the top level created noise and reduced dashboard scan speed.
   - Dashboard should prioritize seeing and deciding, not stuffing all CRUD entry points into the landing page.

3. **Old weekly report raw breakdown layout**
   - Reason: plain `pre` blocks gave data but not decision support.
   - Replaced with throughput, blockers, breakdown, and recent-change framing.

## Added modules and why

These were added because they better match the user’s confirmed goal: balanced execution + management view.

1. **Global Filters bar**
   - Value: creates a single operating scope shared by Dashboard / Kanban / Reports.

2. **Action Center**
   - Value: surfaces next-best actions instead of forcing users to scan the whole board.

3. **Risk & Blockers**
   - Value: isolates interventions needed now, which is higher-value than generic status counts.

4. **Timeline**
   - Value: gives movement context and makes recent change visible without opening Kanban.

5. **Insights panel**
   - Value: provides lightweight management readouts (focus owner, dominant priority, completion ratio, project count).

6. **Scoped weekly reports**
   - Value: reports are now usable for a selected project / owner / status slice instead of only global rollups.

---

## V3 Features

- **登录权限与会话管理**: local password auth + cookie session
- **审批队列（外部动作 gate）**: create/review approvals before external actions
- **Unified filters across Dashboard / Kanban / Reports / API**
- **Dashboard information hierarchy redesign**
- **Kanban scoped by shared query params**
- **Weekly reports scoped by shared query params**
- **REST API (`/api`)**: create/list/get/update/reorder tasks + approval queue + reports
- **Filtered export**: task export via CSV and JSON, honoring current filter scope
- **SQLite safe compatibility**: additive migration for `task.updated_at` and `task.sort_order`

## Tech

- FastAPI + Jinja templates + vanilla JS
- SQLite via SQLModel
- `uv` for env/deps
- Ruff + Pytest + GitHub Actions CI

## Quick Start

```bash
uv sync --all-groups
# auth muted by default (PMC_AUTH_DISABLED=1)
uv run uvicorn app.main:app --reload
```

Open: http://127.0.0.1:8000

### Enable login/auth again (when needed)

```bash
export PMC_AUTH_DISABLED=0
export PMC_ADMIN_USER=admin
export PMC_ADMIN_PASSWORD='change-this-now'
uv run uvicorn app.main:app --reload
```

Open: http://127.0.0.1:8000/login

> First startup auto-seeds admin user from env vars if missing.

## Main Routes

- `/login` - sign in
- `/` - dashboard
- `/kanban` - kanban board
- `/approvals` - approval queue review
- `/reports/weekly` - weekly report UI

## Filter usage guide

### Shared page filters

Use these on Dashboard / Kanban / Reports:

- **Search (`q`)**: matches task title, description, and project
- **Project (`project`)**: exact project scope
- **Status (`status`)**: `backlog | in_progress | blocked | done`
- **Owner (`owner`)**: `lan | peach | joint`
- **Priority (`priority`)**: `low | medium | high`

### API + export behavior

These endpoints also accept the same filter params:

- `GET /api/tasks`
- `GET /api/export/tasks.json`
- `GET /api/export/tasks.csv`
- `GET /api/reports/weekly`

Example:

```bash
curl 'http://127.0.0.1:8000/api/tasks?project=portfolio&owner=lan'
```

## Kanban usage

- **Shared scope**: board contents now come from backend-filtered query params.
- **Drag and drop**: reprioritize within a column or move across columns; order is persisted through `POST /api/tasks/reorder`.
- **Inline edit**: edit title / description directly and click **Save**.
- **Detail modal**: click **Open** or **Details** to edit status, owner, priority, project, due date, and full description.

## Persistence model

Kanban ordering uses `task.sort_order`, added via a safe additive SQLite migration. Existing databases remain compatible; missing columns are created automatically at app startup.

## API Endpoints

### Tasks
- `GET /api/tasks`
- `GET /api/tasks/{task_id}`
- `POST /api/tasks`
- `PATCH /api/tasks/{task_id}`
- `POST /api/tasks/reorder`

### Approvals
- `GET /api/approvals`
- `POST /api/approvals`
- `PATCH /api/approvals/{approval_id}?decision=approved|rejected&note=...`

### Export & Reports
- `GET /api/export/tasks.json`
- `GET /api/export/tasks.csv`
- `GET /api/reports/weekly`

## Tests / Quality Checks

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
```

## Architecture

See `docs/ARCHITECTURE.md` for the earlier V2 design baseline. V3 keeps auth, approvals, routes, and SQLite compatibility intact while upgrading the operating model around unified scope + panel hierarchy.
