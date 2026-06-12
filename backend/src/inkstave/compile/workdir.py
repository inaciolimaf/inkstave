"""Per-compile workdir: creation, safe assembly, output discovery, cleanup (spec 21)."""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Protocol
from uuid import UUID

from inkstave.compile.errors import InputLimitError, UnsafePathError
from inkstave.compile.limits import ResourceLimits
from inkstave.compile.result import CompileArtifact

_TEXT_SUFFIXES = {".log", ".aux", ".out", ".toc", ".txt", ".tex", ".bbl", ".blg"}


class DocumentSource(Protocol):
    """Yields ``(rel_path, content)`` for every text document of a project."""

    def iter_documents(self, project_id: UUID) -> AsyncIterator[tuple[str, str]]: ...


class FileSource(Protocol):
    """Yields ``(rel_path, byte-stream)`` for every binary file of a project."""

    def iter_files(self, project_id: UUID) -> AsyncIterator[tuple[str, AsyncIterator[bytes]]]: ...


@dataclass(slots=True)
class AssembledInputs:
    file_count: int
    total_bytes: int
    paths: list[str] = field(default_factory=list)


def safe_join(base: Path, rel: str) -> Path:
    """Join ``rel`` under ``base``, rejecting absolute paths, ``..`` and symlink escapes."""
    if not rel or rel.startswith("/") or PurePosixPath(rel).is_absolute():
        raise UnsafePathError(f"unsafe path: {rel!r}")
    if any(part == ".." for part in PurePosixPath(rel).parts):
        raise UnsafePathError(f"path traversal: {rel!r}")

    base_resolved = base.resolve()
    candidate = Path(os.path.normpath(base_resolved / rel))
    if candidate != base_resolved and not candidate.is_relative_to(base_resolved):
        raise UnsafePathError(f"path escapes workdir: {rel!r}")

    # Defence in depth: an existing ancestor that is a symlink must not point out.
    probe = candidate
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    if not probe.resolve().is_relative_to(base_resolved):
        raise UnsafePathError(f"symlink escapes workdir: {rel!r}")
    return candidate


async def create_workdir(root: Path, compile_id: UUID) -> Path:
    """Create ``<root>/<compile_id>/`` with ``input/`` and ``output/`` (mode 0700)."""

    def _make() -> Path:
        workdir = root / str(compile_id)
        (workdir / "input").mkdir(parents=True, exist_ok=True)
        (workdir / "output").mkdir(parents=True, exist_ok=True)
        for path in (root, workdir, workdir / "input", workdir / "output"):
            os.chmod(path, 0o700)
        return workdir

    return await asyncio.to_thread(_make)


async def cleanup_workdir(workdir: Path) -> None:
    """Recursively remove the workdir; never raises."""
    await asyncio.to_thread(shutil.rmtree, workdir, ignore_errors=True)


async def assemble_inputs(
    *,
    workdir: Path,
    project_id: UUID,
    docs: DocumentSource,
    files: FileSource,
    limits: ResourceLimits,
) -> AssembledInputs:
    """Materialise all docs + binary files under ``<workdir>/input/`` within limits."""
    input_dir = workdir / "input"
    count = 0
    total = 0
    paths: list[str] = []

    def _bump(extra: int) -> None:
        nonlocal count, total
        count += 1
        total += extra
        if count > limits.max_input_files:
            raise InputLimitError(f"too many input files (> {limits.max_input_files})")
        if total > limits.max_input_bytes:
            raise InputLimitError(f"input too large (> {limits.max_input_bytes} bytes)")

    async for rel, content in docs.iter_documents(project_id):
        dest = safe_join(input_dir, rel)
        data = content.encode("utf-8")
        _bump(len(data))
        await asyncio.to_thread(dest.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(dest.write_bytes, data)
        paths.append(rel)

    async for rel, stream in files.iter_files(project_id):
        dest = safe_join(input_dir, rel)
        await asyncio.to_thread(dest.parent.mkdir, parents=True, exist_ok=True)
        size = 0
        handle = await asyncio.to_thread(open, dest, "wb")
        try:
            async for chunk in stream:
                size += len(chunk)
                total += len(chunk)
                if total > limits.max_input_bytes:
                    raise InputLimitError(f"input too large (> {limits.max_input_bytes} bytes)")
                await asyncio.to_thread(handle.write, chunk)
        finally:
            await asyncio.to_thread(handle.close)
            # Close the source stream (async generator) so a partially-consumed
            # input on an early error path does not leak the underlying handle.
            aclose = getattr(stream, "aclose", None)
            if aclose is not None:
                with contextlib.suppress(Exception):
                    await aclose()
        count += 1
        if count > limits.max_input_files:
            raise InputLimitError(f"too many input files (> {limits.max_input_files})")
        paths.append(rel)

    return AssembledInputs(file_count=count, total_bytes=total, paths=paths)


def _content_type(name: str) -> str:
    lower = name.lower()
    if lower.endswith(".pdf"):
        return "application/pdf"
    if lower.endswith(".synctex.gz") or lower.endswith(".gz"):
        return "application/gzip"
    if Path(lower).suffix in _TEXT_SUFFIXES:
        return "text/plain"
    return "application/octet-stream"


def collect_outputs(output_dir: Path) -> list[CompileArtifact]:
    """Walk the output dir and classify every file into a :class:`CompileArtifact`."""
    artifacts: list[CompileArtifact] = []
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(output_dir).as_posix()
        artifacts.append(
            CompileArtifact(
                name=path.name,
                rel_path=rel,
                abs_path=path,
                size_bytes=path.stat().st_size,
                content_type=_content_type(path.name),
            )
        )
    return artifacts
