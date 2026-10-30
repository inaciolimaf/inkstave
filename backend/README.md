# Inkstave backend

The FastAPI application: a modular monolith in `src/inkstave/`, with Alembic migrations in
`migrations/` and tests in `tests/`. How it is built: [`docs/system/overview.md`](../docs/system/overview.md).

Managed with [`uv`](https://docs.astral.sh/uv/). From the repo root:

```bash
make install-backend     # install from uv.lock
make lint                # ruff, format check, size ceilings, import contracts
make types               # strict mypy
make test                # unit + integration
```
