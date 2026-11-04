"""Spec 121 §5.4 step 1: the pre-receive rules. Every bad path is named, and one problem refuses the push."""

from __future__ import annotations

import base64

import pytest

from inkstave.core.config.settings import get_settings
from inkstave.modules.auth import hash_token
from inkstave.modules.git.auth.tokens import TOKEN_PREFIX, basic_password, display_prefix, new_raw_token
from inkstave.modules.git.push.changes import FileWrite, PushChanges, kind_of, validate_changes

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
PDF = b"%PDF-1.4\n" + b"\x00" * 32
REGULAR = 0o100644


def _write(*parts: str, data: bytes = b"hello\n", old: bytes | None = None) -> FileWrite:
    return FileWrite(parts=tuple(parts), data=data, old=old, mode=REGULAR)


def _problems(changes: PushChanges, **overrides: object) -> list[str]:
    settings = get_settings().model_copy(update=overrides)
    return validate_changes(changes, settings)


def test_a_clean_push_has_no_problems() -> None:
    changes = PushChanges(
        writes=[_write("main.tex", data=b"\\documentclass{article}\n"), _write("img", "a.png", data=PNG)],
        paths=[("main.tex",), ("img", "a.png")],
        folder_count=1,
    )
    assert _problems(changes) == []


@pytest.mark.parametrize(
    "bad_path",
    [
        ("..", "evil.tex"),
        (".", "x.tex"),
        ("a\\b.tex",),
        ("con.tex",),
        (".DS_Store",),
        ("__MACOSX", "x.tex"),
        ("trailing.",),
        (" lead.tex",),
    ],
)
def test_unsafe_names_are_refused_per_path(bad_path: tuple[str, ...]) -> None:
    changes = PushChanges(writes=[_write(*bad_path)], paths=[bad_path])
    problems = _problems(changes)
    assert problems, bad_path
    assert problems[0].startswith("/".join(bad_path) + ":")


def test_unknown_extension_is_refused() -> None:
    changes = PushChanges(writes=[_write("setup.exe", data=b"MZ\x00")], paths=[("setup.exe",)])
    assert _problems(changes) == ["setup.exe: this file type is not allowed"]


def test_binary_file_over_the_upload_limit_is_refused() -> None:
    big = PNG + b"x" * 100
    changes = PushChanges(writes=[_write("big.png", data=big)], paths=[("big.png",)])
    problems = _problems(changes, max_upload_bytes=50)
    assert problems and "larger than the upload limit" in problems[0]


def test_content_must_match_the_extension() -> None:
    changes = PushChanges(writes=[_write("fake.png", data=PDF)], paths=[("fake.png",)])
    assert _problems(changes) == ["fake.png: file content does not match its extension or an allowed type"]


def test_text_must_be_utf8_and_under_the_document_limit() -> None:
    bad = PushChanges(writes=[_write("main.tex", data=b"\xff\xfe bad")], paths=[("main.tex",)])
    assert _problems(bad) == ["main.tex: text is not valid UTF-8"]
    long = PushChanges(writes=[_write("main.tex", data=b"a" * 100)], paths=[("main.tex",)])
    assert "larger than" in _problems(long, max_document_bytes=10)[0]


def test_names_that_differ_only_in_case_clash() -> None:
    changes = PushChanges(
        writes=[_write("Main.tex"), _write("main.tex")],
        paths=[("Main.tex",), ("main.tex",)],
    )
    problems = _problems(changes)
    assert any("clashes with" in problem for problem in problems)


def test_a_symlink_is_refused() -> None:
    link = FileWrite(parts=("link.tex",), data=b"target", old=None, mode=0o120000)
    assert _problems(PushChanges(writes=[link], paths=[("link.tex",)])) == [
        "link.tex: symlinks and submodules are not supported"
    ]


def test_the_node_cap_counts_files_and_folders() -> None:
    paths = [("a", "b", "c.tex"), ("a", "d.tex")]
    changes = PushChanges(paths=paths, folder_count=2)
    problems = _problems(changes, tree_max_nodes=3)
    assert problems == ["the project would hold 4 entries, the limit is 3"]


def test_kind_of_follows_the_text_and_upload_rules() -> None:
    settings = get_settings()
    assert kind_of("main.tex", settings) == "text"
    assert kind_of("notes.txt", settings) == "text"
    assert kind_of("figure.png", settings) == "file"
    assert kind_of("program.exe", settings) is None


def test_basic_password_takes_the_token_after_the_user_name() -> None:
    raw = new_raw_token()
    header = "Basic " + base64.b64encode(f"anyone:{raw}".encode()).decode()
    assert basic_password(header) == raw
    assert basic_password(None) is None
    assert basic_password("Bearer abc") is None
    assert basic_password("Basic " + base64.b64encode(b"nopassword").decode()) is None


def test_new_tokens_have_the_prefix_and_hash_to_a_fixed_digest() -> None:
    raw = new_raw_token()
    assert raw.startswith(TOKEN_PREFIX) and len(raw) == len(TOKEN_PREFIX) + 43
    assert display_prefix(raw) == raw[:12]
    assert hash_token(raw) != raw
    assert len(hash_token(raw)) == 64
