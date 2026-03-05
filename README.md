# Peach Mission Control

Mission-control dashboard for Lan + Peach collaboration.

## Features (MVP)
- Task management (status, priority, owner, due date)
- Project tracking (active/completed)
- Job application pipeline (discovered/applied/interview/offer/rejected)
- Daily dashboard metrics
- Quick capture form for new work items

## Tech
- FastAPI + Jinja templates
- SQLite via SQLModel
- `uv` for env/deps
- Ruff + Pytest + GitHub Actions CI

## Run
```bash
uv sync --all-groups
uv run uvicorn app.main:app --reload
```
Open: http://127.0.0.1:8000

## Testing
```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## How we use this going forward
- All new tasks between Lan and Peach should be logged here first.
- External actions still require explicit approval gates.
