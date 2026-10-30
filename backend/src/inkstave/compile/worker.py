"""Deployment entrypoint: ``arq inkstave.compile.worker.WorkerSettings``.

The compose files and the Dockerfile name this path; the worker lives in ``inkstave.worker``.
"""

from inkstave.worker import WorkerSettings

__all__ = ["WorkerSettings"]
