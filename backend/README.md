# Inkstave backend

This is the Inkstave **FastAPI backend**. At spec 01 it is only a project
skeleton (package layout + `uv` tooling); the FastAPI application, settings,
routers, database models and async jobs are added by later specs (02 onwards).

Managed with [`uv`](https://docs.astral.sh/uv/). From the repo root:

```bash
uv sync --project backend     # resolve + install dev tooling
uv run ruff check backend     # lint
uv run mypy backend/src       # type-check
```
