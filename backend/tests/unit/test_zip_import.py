"""Unit tests for the zip-import core: planning, encoding, root-doc detection (spec 101).

All exercised over tiny in-memory zips; caps are tested with small limits so no
real large data is needed (sizes come from the central directory).
"""

from __future__ import annotations

import io
import zipfile

import pytest

from inkstave.services.zip_import import (
    EmptyArchiveError,
    ImportLimits,
    PlannedEntry,
    SymlinkEntryError,
    ZipBombError,
    ZipEntryCountError,
    ZipSlipError,
    decode_text,
    detect_root_doc,
    plan_entries,
)


def _limits(
    *,
    max_uncompressed: int = 10_000_000,
    max_file: int = 10_000_000,
    max_entries: int = 1000,
    exts: frozenset[str] | None = None,
) -> ImportLimits:
    return ImportLimits(
        max_zip_bytes=50_000_000,
        max_uncompressed_bytes=max_uncompressed,
        max_file_bytes=max_file,
        max_entries=max_entries,
        allowed_extensions=exts or frozenset({".tex", ".bib", ".png", ".pdf"}),
    )


def _zip(entries: dict[str, bytes]) -> zipfile.ZipFile:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    buf.seek(0)
    return zipfile.ZipFile(buf)


def _symlink_zip(name: str, target: bytes) -> zipfile.ZipFile:
    import stat as _stat

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        info = zipfile.ZipInfo(name)
        info.external_attr = (_stat.S_IFLNK | 0o777) << 16
        zf.writestr(info, target)
    buf.seek(0)
    return zipfile.ZipFile(buf)


# --------------------------------------------------------------------------- #
# plan_entries — happy path
# --------------------------------------------------------------------------- #


def test_plan_happy_path_classifies_and_counts() -> None:
    zf = _zip(
        {
            "main.tex": b"\\documentclass{article}",
            "chapters/intro.tex": b"hello",
            "refs.bib": b"@book{x}",
            "figures/diagram.png": b"\x89PNG\r\n\x1a\n",
        }
    )
    plan = plan_entries(zf, _limits())
    assert plan.skipped == 0
    kinds = {e.parts: e.classification for e in plan.entries}
    assert kinds[("main.tex",)] == "text"
    assert kinds[("chapters", "intro.tex")] == "text"
    assert kinds[("figures", "diagram.png")] == "binary"


def test_plan_skips_disallowed_extension_not_fatal() -> None:
    plan = plan_entries(_zip({"main.tex": b"x", "notes.exe": b"MZ"}), _limits())
    assert plan.skipped == 1
    assert {e.parts for e in plan.entries} == {("main.tex",)}


def test_plan_ignores_junk_silently() -> None:
    zf = _zip(
        {
            "main.tex": b"x",
            "__MACOSX/._main.tex": b"junk",
            ".git/config": b"junk",
            "figures/.DS_Store": b"junk",
        }
    )
    plan = plan_entries(zf, _limits())
    assert plan.skipped == 0
    assert {e.parts for e in plan.entries} == {("main.tex",)}


def test_plan_empty_archive_raises() -> None:
    with pytest.raises(EmptyArchiveError):
        plan_entries(_zip({"notes.exe": b"MZ", "__MACOSX/x": b"j"}), _limits())


# --------------------------------------------------------------------------- #
# plan_entries — security: zip-slip, symlink, bombs
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("name", ["../../etc/passwd", "/etc/passwd", "a/../../b", "..\\..\\x"])
def test_plan_rejects_zip_slip(name: str) -> None:
    with pytest.raises(ZipSlipError):
        plan_entries(_zip({name: b"x"}), _limits())


def test_plan_rejects_dot_segment() -> None:
    with pytest.raises(ZipSlipError):
        plan_entries(_zip({"./main.tex": b"x"}), _limits())


def test_plan_rejects_symlink() -> None:
    with pytest.raises(SymlinkEntryError):
        plan_entries(_symlink_zip("link.tex", b"/etc/passwd"), _limits())


def test_plan_rejects_oversize_total_before_decompress() -> None:
    zf = _zip({"a.tex": b"hello", "b.tex": b"world"})  # 10 bytes total
    with pytest.raises(ZipBombError):
        plan_entries(zf, _limits(max_uncompressed=8))


def test_plan_rejects_oversize_single_file() -> None:
    with pytest.raises(ZipBombError):
        plan_entries(_zip({"a.tex": b"hello"}), _limits(max_file=3))


def test_plan_rejects_too_many_entries() -> None:
    entries = {f"f{i}.tex": b"x" for i in range(5)}
    with pytest.raises(ZipEntryCountError):
        plan_entries(_zip(entries), _limits(max_entries=3))


# --------------------------------------------------------------------------- #
# decode_text
# --------------------------------------------------------------------------- #


def test_decode_latin1_without_raising() -> None:
    raw = "café résumé".encode("latin-1")
    assert decode_text(raw) == "café résumé"


def test_decode_cp1252_smart_quotes() -> None:
    raw = "“hi”".encode("cp1252")
    assert decode_text(raw) == "“hi”"


def test_decode_strips_bom_and_normalises_newlines() -> None:
    raw = b"\xef\xbb\xbfline1\r\nline2\rline3"
    assert decode_text(raw) == "line1\nline2\nline3"


# --------------------------------------------------------------------------- #
# detect_root_doc
# --------------------------------------------------------------------------- #


def _entry(*parts: str) -> PlannedEntry:
    return PlannedEntry(
        zip_name="/".join(parts),
        parts=parts,
        is_dir=False,
        uncompressed_size=1,
        classification="text",
    )


def test_detect_root_prefers_documentclass_over_main() -> None:
    paper = _entry("paper.tex")
    main = _entry("main.tex")
    blobs = {("paper.tex",): b"\\documentclass{article}", ("main.tex",): b"no class here"}
    assert detect_root_doc([paper, main], blobs) == ("paper.tex",)


def test_detect_root_shallowest_documentclass_wins() -> None:
    deep = _entry("src", "deep.tex")
    top = _entry("top.tex")
    blobs = {
        ("src", "deep.tex"): b"\\documentclass{article}",
        ("top.tex",): b"\\documentclass{book}",
    }
    assert detect_root_doc([deep, top], blobs) == ("top.tex",)


def test_detect_root_falls_back_to_top_level_main() -> None:
    main = _entry("main.tex")
    other = _entry("other.tex")
    blobs = {("main.tex",): b"no class", ("other.tex",): b"also none"}
    assert detect_root_doc([main, other], blobs) == ("main.tex",)


def test_detect_root_single_tex_fallback() -> None:
    only = _entry("thesis.tex")
    assert detect_root_doc([only], {("thesis.tex",): b"no class"}) == ("thesis.tex",)


def test_detect_root_none_when_ambiguous_no_class() -> None:
    a = _entry("a.tex")
    b = _entry("b.tex")
    assert detect_root_doc([a, b], {("a.tex",): b"x", ("b.tex",): b"y"}) is None
