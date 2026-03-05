# Peach Mission Control V2 Architecture

## Goals
V2 introduces secure local access, explicit external-action approval gating, kanban execution tracking, API integration surfaces, and reporting/export capabilities.

## Layers

- **Web/UI layer** (`app/main.py` + Jinja templates)
  - Authenticated dashboard (`/`)
  - Kanban board (`/kanban`)
  - Approval queue review screen (`/approvals`)
  - Weekly report page (`/reports/weekly`)
- **API layer** (`/api/*` in `app/main.py`)
  - Task CRUD (create/list/update)
  - Approval queue create/list/review
  - Export endpoints (JSON/CSV)
  - Weekly report endpoint
- **Persistence layer** (`app/models.py`, `app/db.py`)
  - SQLModel entities for tasks, users, sessions, approvals
  - SQLite engine
  - Migration-safe startup hook (`migrate_db`) for non-breaking schema evolution

## Security Model (Pragmatic)

- Local username/password auth with PBKDF2-SHA256 password hashing
- HttpOnly session cookie (`pmc_session`) mapped to DB-backed session tokens
- All HTML app routes (except `/login`) and all `/api/*` endpoints require authentication
- External actions should be inserted into `ApprovalRequest` as `pending` before execution

## Approval Gate Pattern

1. Producer (UI/API/chat automation) creates approval request via `/api/approvals`.
2. Request lands in queue with `pending` state.
3. Human reviewer approves/rejects in `/approvals` or `/api/approvals/{id}`.
4. Downstream external action runner executes only when status is `approved`.

## Reporting

Weekly report computes a rolling 7-day summary:

- tasks touched / done / blocked
- status and owner breakdown
- approvals created and pending

## Data Export

- `/api/export/tasks.json` for system-to-system import
- `/api/export/tasks.csv` for spreadsheet workflows and manual review
