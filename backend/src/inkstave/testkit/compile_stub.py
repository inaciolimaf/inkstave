"""A deterministic Tectonic runner stub for the e2e smoke tier (spec 54).

``MockTectonicRunner`` implements the :class:`~inkstave.compile.runner.TectonicRunner`
protocol but never spawns a subprocess. It writes a tiny, valid single-page PDF
plus a canned log into the compile ``output_dir`` so the real
:class:`~inkstave.compile.service.CompileService` collects them exactly as it
would a real Tectonic run. This keeps ``COMPILE_MODE=mock`` instant and offline.

A deliberate-error path lets the compile journey assert that LaTeX errors surface
in the log/annotations: if the assembled main document contains the sentinel
``% INKSTAVE_E2E_COMPILE_ERROR`` (or an ``\\inkstaveforceerror`` command), the
runner emits a realistic LaTeX error log and reports a non-zero exit with no PDF.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from inkstave.compile.limits import CancelToken, ResourceLimits
from inkstave.compile.result import RunOutcome

#: Sentinels a document can include to force the mocked compile to fail.
ERROR_SENTINELS = ("% INKSTAVE_E2E_COMPILE_ERROR", "\\inkstaveforceerror")

_SUCCESS_LOG = """This is Tectonic (mock), Version 0.0.0-e2e
(./{stem}.tex
LaTeX2e <2024-01-01>
(./article.cls)
Output written on {stem}.pdf (1 page).
Transcript written on {stem}.log.
"""

# A realistic LaTeX error transcript so the spec-27 log parser produces an
# annotation (an "Undefined control sequence" with an ``l.NN`` source line).
_ERROR_LOG = """This is Tectonic (mock), Version 0.0.0-e2e
(./{stem}.tex
LaTeX2e <2024-01-01>
(./article.cls)
! Undefined control sequence.
l.{line} \\inkstaveforceerror

No pages of output.
Transcript written on {stem}.log.
"""


def build_minimal_pdf(text: str = "Inkstave E2E") -> bytes:
    """Build a valid, single-page PDF (correct xref) that PDF.js renders.

    Kept tiny and dependency-free; offsets are computed so the cross-reference
    table is well-formed and the document opens without recovery.
    """
    safe = "".join(ch for ch in text if 32 <= ord(ch) < 127).replace("(", " ").replace(")", " ")
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        ("BT /F1 24 Tf 72 720 Td (" + safe + ") Tj ET").encode("latin-1"),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        if i == 4:  # the content stream object
            stream = body
            out += (f"{i} 0 obj\n<< /Length {len(stream)} >>\nstream\n").encode("latin-1")
            out += stream
            out += b"\nendstream\nendobj\n"
        else:
            out += f"{i} 0 obj\n".encode("latin-1") + body + b"\nendobj\n"

    xref_pos = len(out)
    count = len(objects) + 1
    out += f"xref\n0 {count}\n".encode("latin-1")
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode("latin-1")
    out += (f"trailer\n<< /Size {count} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n").encode(
        "latin-1"
    )
    return bytes(out)


#: Pre-built canned PDF reused for every mocked successful compile.
CANNED_PDF: bytes = build_minimal_pdf("Inkstave E2E")


class MockTectonicRunner:
    """A :class:`TectonicRunner` that emits a canned PDF/log without a subprocess."""

    async def run(
        self,
        *,
        workdir: Path,
        main_file: str,
        output_dir: Path,
        timeout_s: int,
        limits: ResourceLimits,
        cancel: CancelToken,
    ) -> RunOutcome:
        # Blocking disk I/O is tiny here, but offload it so this stays a clean
        # async runner (matching the real one's non-blocking contract).
        return await asyncio.to_thread(self._run_sync, workdir, main_file, output_dir)

    @staticmethod
    def _run_sync(workdir: Path, main_file: str, output_dir: Path) -> RunOutcome:
        stem = Path(main_file).stem
        output_dir.mkdir(parents=True, exist_ok=True)

        source = ""
        main_path = workdir / "input" / main_file
        if main_path.is_file():
            source = main_path.read_text("utf-8", "replace")

        if any(sentinel in source for sentinel in ERROR_SENTINELS):
            line = _sentinel_line(source)
            log = _ERROR_LOG.format(stem=stem, line=line)
            (output_dir / f"{stem}.log").write_text(log, "utf-8")
            return RunOutcome(
                exit_code=1,
                stdout=log,
                stderr="",
                timed_out=False,
                cancelled=False,
                duration_ms=1,
            )

        (output_dir / f"{stem}.pdf").write_bytes(CANNED_PDF)
        log = _SUCCESS_LOG.format(stem=stem)
        (output_dir / f"{stem}.log").write_text(log, "utf-8")
        return RunOutcome(
            exit_code=0,
            stdout=log,
            stderr="",
            timed_out=False,
            cancelled=False,
            duration_ms=1,
        )


def _sentinel_line(source: str) -> int:
    for i, line in enumerate(source.splitlines(), start=1):
        if any(sentinel in line for sentinel in ERROR_SENTINELS):
            return i
    return 1
