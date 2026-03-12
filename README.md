# Peach Mission Control (V2)

Mission-control dashboard for Lan + Peach collaboration, now with auth, approval gate queue, an upgraded Asana-like kanban workflow, API endpoints, export, and weekly retros.

## V2 Features

- **登录权限与会话管理**: local password auth + cookie session
- **审批队列（外部动作 gate）**: create/review approvals before external actions
- **Kanban 视图升级**:
  - search + filter（owner / priority / status）
  - desktop-first 4-column board
  - cross-column drag and drop with persisted order
  - inline edit for title / description
  - task detail modal for full-card editing
- **REST API (`/api`)**: create/list/get/update/reorder tasks + approval queue + reports
- **数据导出**: task export via CSV and JSON
- **每周复盘**: weekly summary page and API endpoint
- **SQLite 安全迁移**: auto-additive migration for `task.updated_at` and `task.sort_order`

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

## Kanban Usage

### Core interactions

- **Search**: use the top search input to match task title, description, and project.
- **Filters**: narrow the board by owner, priority, or a status chip.
- **Drag and drop**: drag a card within a column to reprioritize, or into another column to change status. Order is persisted to SQLite through `POST /api/tasks/reorder`.
- **Inline edit**: directly edit card title/description and click **Save**.
- **Detail modal**: click **Open** or **Details** to edit status, owner, priority, project, due date, and full description.

### Persistence model

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

See `docs/ARCHITECTURE.md` for the V2 design, auth model, approval-gate flow, and migration approach.
