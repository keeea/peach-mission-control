# Peach Mission Control (V2)

Mission-control dashboard for Lan + Peach collaboration, now with auth, approval gate queue, kanban workflow, API endpoints, export, and weekly retros.

## V2 Features

- **登录权限与会话管理**: local password auth + cookie session
- **审批队列（外部动作 gate）**: create/review approvals before external actions
- **Kanban 视图**: backlog / in_progress / blocked / done, with move actions
- **REST API (`/api`)**: create/list/update tasks + approval queue + reports
- **数据导出**: task export via CSV and JSON
- **每周复盘**: weekly summary page and API endpoint

## Tech

- FastAPI + Jinja templates
- SQLite via SQLModel
- `uv` for env/deps
- Ruff + Pytest + GitHub Actions CI

## Quick Start

```bash
uv sync --all-groups
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

## API Endpoints

### Tasks
- `GET /api/tasks`
- `POST /api/tasks`
- `PATCH /api/tasks/{task_id}`

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
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## Architecture

See `docs/ARCHITECTURE.md` for the V2 design, auth model, approval-gate flow, and migration approach.
