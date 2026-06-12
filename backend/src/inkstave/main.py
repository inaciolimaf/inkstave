"""Uvicorn entrypoint target: ``inkstave.main:app``."""

from __future__ import annotations

from inkstave.app import create_app

app = create_app()
