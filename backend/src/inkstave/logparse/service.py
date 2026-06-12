"""Log-problems service: resolve a compile's log, parse it, count, cap (spec 27)."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING
from uuid import UUID

from inkstave.logparse.latex_log_parser import parse_latex_log
from inkstave.logparse.models import CompileProblems, Problem, ProblemSeverity

if TYPE_CHECKING:
    from inkstave.compile.outputs import OutputStore
    from inkstave.compile.repository import CompileRepository
    from inkstave.config import Settings
    from inkstave.db.models.compile import Compile

logger = logging.getLogger(__name__)


class LogNotAvailable(Exception):
    """The requested compile has no usable ``output.log``."""


class LogProblemsService:
    def __init__(
        self, *, repo: CompileRepository, output_store: OutputStore, settings: Settings
    ) -> None:
        self._repo = repo
        self._store = output_store
        self._settings = settings

    async def _resolve_compile(self, project_id: UUID, compile_id: str | None) -> Compile:
        if compile_id and compile_id != "latest":
            try:
                cid = UUID(compile_id)
            except ValueError as exc:
                raise LogNotAvailable() from exc
            row = await self._repo.get(project_id, cid)
        else:
            row = await self._repo.get_latest(project_id)
        if row is None:
            raise LogNotAvailable()
        return row

    async def problems_for(self, project_id: UUID, compile_id: str | None) -> CompileProblems:
        row = await self._resolve_compile(project_id, compile_id)
        obj = await self._store.open_log(row.id)
        if obj is None:
            raise LogNotAvailable()

        data = b"".join([chunk async for chunk in obj.stream()])
        truncated = False
        limit = self._settings.logparse_max_log_bytes
        if len(data) > limit:
            # Keep the TAIL (last `limit` bytes), not the beginning. This
            # intentionally supersedes the imprecise spec §5.5 wording ("truncated
            # from the end") per ADR 0027: for LaTeX the final, actionable errors
            # live at the end of the log, so the tail is the slice worth parsing.
            data = data[-limit:]
            truncated = True
            logger.warning("log for compile %s truncated to %d bytes for parsing", row.id, limit)
        text = data.decode("utf-8", "replace")

        problems = await asyncio.to_thread(
            parse_latex_log,
            text,
            root_file=row.main_file,
            wrap_width=self._settings.logparse_wrap_width,
        )

        if truncated:
            problems.insert(
                0,
                Problem(
                    severity=ProblemSeverity.info,
                    message="Log was truncated before parsing (too large).",
                    raw="",
                    rule="log-truncated",
                ),
            )

        cap = self._settings.logparse_max_problems
        if len(problems) > cap:
            omitted = len(problems) - cap
            problems = problems[:cap]
            problems.append(
                Problem(
                    severity=ProblemSeverity.info,
                    message=f"{omitted} more problems omitted.",
                    raw="",
                    rule="too-many-problems",
                )
            )

        errors = sum(p.severity is ProblemSeverity.error for p in problems)
        warnings = sum(p.severity is ProblemSeverity.warning for p in problems)
        infos = sum(p.severity is ProblemSeverity.info for p in problems)
        return CompileProblems(
            compile_id=str(row.id),
            errors=errors,
            warnings=warnings,
            infos=infos,
            problems=problems,
        )
