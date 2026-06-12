"""Unit tests for compile workdir assembly, path safety and cleanup (spec 21)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import pytest

from inkstave.compile.errors import InputLimitError, UnsafePathError
from inkstave.compile.limits import ResourceLimits
from inkstave.compile.workdir import (
    assemble_inputs,
    cleanup_workdir,
    collect_outputs,
    create_workdir,
    safe_join,
)


def _limits(**over: int | None) -> ResourceLimits:
    base: dict[str, int | None] = {
        "max_input_files": 100,
        "max_input_bytes": 1_000_000,
        "max_output_bytes": 1_000_000,
        "max_log_bytes": 1_000_000,
        "max_stdout_bytes": 1_000_000,
        "cpu_seconds": None,
        "address_space_bytes": None,
    }
    base.update(over)
    return ResourceLimits(**base)  # type: ignore[arg-type]


class FakeDocs:
    def __init__(self, docs: list[tuple[str, str]]) -> None:
        self._docs = docs

    async def iter_documents(self, project_id: object) -> AsyncIterator[tuple[str, str]]:
        for path, content in self._docs:
            yield path, content


class FakeFiles:
    def __init__(self, files: list[tuple[str, bytes]]) -> None:
        self._files = files

    async def iter_files(
        self, project_id: object
    ) -> AsyncIterator[tuple[str, AsyncIterator[bytes]]]:
        for path, data in self._files:

            async def stream(payload: bytes = data) -> AsyncIterator[bytes]:
                yield payload

            yield path, stream()


# --- safe_join ------------------------------------------------------------- #


def test_safe_join_accepts_in_tree(tmp_path: Path) -> None:
    assert safe_join(tmp_path, "a/b.tex") == tmp_path.resolve() / "a" / "b.tex"


@pytest.mark.parametrize("bad", ["/etc/passwd", "../escape", "a/../../escape", ""])
def test_safe_join_rejects_unsafe(tmp_path: Path, bad: str) -> None:
    with pytest.raises(UnsafePathError):
        safe_join(tmp_path, bad)


def test_safe_join_rejects_symlink_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside"
    outside.mkdir()
    base = tmp_path / "base"
    base.mkdir()
    (base / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(UnsafePathError):
        safe_join(base, "link/x.tex")


# --- workdir lifecycle ----------------------------------------------------- #


async def test_create_workdir_makes_input_output(tmp_path: Path) -> None:
    cid = uuid4()
    workdir = await create_workdir(tmp_path, cid)
    assert workdir == tmp_path / str(cid)
    assert (workdir / "input").is_dir()
    assert (workdir / "output").is_dir()
    assert (workdir.stat().st_mode & 0o777) == 0o700


async def test_assemble_writes_docs_and_files(tmp_path: Path) -> None:
    workdir = await create_workdir(tmp_path, uuid4())
    docs = FakeDocs([("main.tex", "hello"), ("chapters/intro.tex", "intro")])
    files = FakeFiles([("img/logo.png", b"\x89PNG")])
    result = await assemble_inputs(
        workdir=workdir, project_id=uuid4(), docs=docs, files=files, limits=_limits()
    )
    assert result.file_count == 3
    assert result.total_bytes == len(b"hello") + len(b"intro") + len(b"\x89PNG")
    assert (workdir / "input" / "main.tex").read_text() == "hello"
    assert (workdir / "input" / "chapters" / "intro.tex").read_text() == "intro"
    assert (workdir / "input" / "img" / "logo.png").read_bytes() == b"\x89PNG"


async def test_assemble_rejects_traversal(tmp_path: Path) -> None:
    workdir = await create_workdir(tmp_path, uuid4())
    docs = FakeDocs([("../../etc/passwd", "x")])
    with pytest.raises(UnsafePathError):
        await assemble_inputs(
            workdir=workdir, project_id=uuid4(), docs=docs, files=FakeFiles([]), limits=_limits()
        )


async def test_assemble_enforces_file_count(tmp_path: Path) -> None:
    workdir = await create_workdir(tmp_path, uuid4())
    docs = FakeDocs([("a.tex", "a"), ("b.tex", "b")])
    with pytest.raises(InputLimitError):
        await assemble_inputs(
            workdir=workdir,
            project_id=uuid4(),
            docs=docs,
            files=FakeFiles([]),
            limits=_limits(max_input_files=1),
        )


async def test_assemble_enforces_byte_cap(tmp_path: Path) -> None:
    workdir = await create_workdir(tmp_path, uuid4())
    docs = FakeDocs([("a.tex", "x" * 100)])
    with pytest.raises(InputLimitError):
        await assemble_inputs(
            workdir=workdir,
            project_id=uuid4(),
            docs=docs,
            files=FakeFiles([]),
            limits=_limits(max_input_bytes=10),
        )


def test_collect_outputs_classifies(tmp_path: Path) -> None:
    out = tmp_path / "output"
    out.mkdir()
    (out / "main.pdf").write_bytes(b"%PDF-1.7")
    (out / "main.log").write_text("log")
    (out / "main.synctex.gz").write_bytes(b"\x1f\x8b")
    artifacts = {a.name: a for a in collect_outputs(out)}
    assert artifacts["main.pdf"].content_type == "application/pdf"
    assert artifacts["main.log"].content_type == "text/plain"
    assert artifacts["main.synctex.gz"].content_type == "application/gzip"


async def test_cleanup_removes_workdir(tmp_path: Path) -> None:
    workdir = await create_workdir(tmp_path, uuid4())
    assert workdir.exists()
    await cleanup_workdir(workdir)
    assert not workdir.exists()
    # Never raises on a missing dir.
    await cleanup_workdir(workdir)
