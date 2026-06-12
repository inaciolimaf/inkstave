"""Spec-58 documentation tests: presence/sections, env-var coverage, internal
link integrity, OpenAPI sync, and the no-Overleaf-code originality clause.

Pure file/string checks plus one in-memory OpenAPI export — fully in budget.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
_DOCS = _ROOT / "docs"


# --- §7.1/7.2/7.4/7.5/7.7/7.10: required docs and their section headings ------ #

_REQUIRED_SECTIONS: dict[str, list[str]] = {
    "README.md": [
        "Screenshots",
        "Quickstart",
        "Tech stack",
        "Documentation",
        "Licensing & originality",
    ],
    "CONTRIBUTING.md": [
        "Development setup",
        "Running the test suite",
        "The spec-driven workflow",
        "Conventions",
        "Originality — no Overleaf code (read this)",
        "Pull-request checklist",
    ],
    "docs/README.md": ["Guides"],
    "docs/user-guide.md": [
        "Account",
        "Projects",
        "The editor",
        "Compiling",
        "SyncTeX",
        "Version history",
        "Collaboration",
        "The AI agent",
    ],
    "docs/admin-guide.md": [
        "Deployment",
        "Configuration (environment variables)",
        "First run",
        "Scaling",
        "Backups & restore",
        "LaTeX package management",
        "Observability",
        "Upgrades",
        "Troubleshooting",
    ],
    "docs/architecture.md": [
        "Service inventory",
        "Data-flow diagrams",
        "Data model overview",
        "Architecture Decision Records",
    ],
    "docs/api-reference.md": [
        "Viewing the live docs",
        "Regenerating the artifact",
        "Authentication",
        "Endpoint groups",
    ],
    # Spec-60 DoD items 5 & 6: these deliverables must exist (regression guard).
    "docs/originality-audit.md": ["Reproducible checks"],
    "docs/release-checklist.md": ["1. Quality gates (local or CI)"],
}

# §5.1 documents that docs/README.md must link to (AC 7.10). If any link is
# removed, the README-links test below must fail.
_README_LINKED_DOCS = (
    "user-guide.md",
    "admin-guide.md",
    "architecture.md",
    "api-reference.md",
    "api/openapi.json",
)


def _headings(text: str) -> set[str]:
    return {m.group(1).strip() for m in re.finditer(r"^#{1,6}\s+(.+?)\s*#*$", text, re.MULTILINE)}


@pytest.mark.parametrize("rel, sections", _REQUIRED_SECTIONS.items())
def test_doc_exists_with_required_sections(rel: str, sections: list[str]) -> None:
    path = _ROOT / rel
    assert path.is_file(), f"missing doc: {rel}"
    headings = _headings(path.read_text("utf-8"))
    missing = [s for s in sections if s not in headings]
    assert missing == [], f"{rel} missing sections: {missing}"


def test_docs_readme_links_every_section_5_1_document() -> None:
    # AC 7.10: docs/README.md must link to every §5.1 document. Asserting the link
    # targets (not just a "Guides" heading) makes this fail if any link is removed.
    text = (_DOCS / "README.md").read_text("utf-8")
    targets = {t.strip() for t in re.findall(r"\]\(([^)]+)\)", text)}
    missing = [doc for doc in _README_LINKED_DOCS if doc not in targets]
    assert missing == [], f"docs/README.md missing links to: {missing}"


def test_architecture_has_four_dataflow_diagrams() -> None:
    text = (_DOCS / "architecture.md").read_text("utf-8")
    for sub in ("Request flow", "Compile flow", "Collaboration / CRDT flow", "Agent flow"):
        assert sub in text, f"architecture.md missing diagram: {sub}"
    assert text.count("```mermaid") >= 4, "expected at least four Mermaid diagrams"


def test_user_guide_states_agent_needs_approval() -> None:
    text = (_DOCS / "user-guide.md").read_text("utf-8").lower()
    assert "never changes your documents on its own" in text
    assert "apply" in text and "review" in text


# --- §7.3: every .env.example variable appears in the admin guide ------------- #


def test_admin_guide_documents_every_env_var() -> None:
    env = (_ROOT / ".env.example").read_text("utf-8")
    names = {
        m.group(1) for line in env.splitlines() if (m := re.match(r"^([A-Z][A-Z0-9_]*)=", line))
    }
    guide = (_DOCS / "admin-guide.md").read_text("utf-8")
    undocumented = sorted(n for n in names if f"`{n}`" not in guide)
    assert undocumented == [], f"env vars missing from the admin guide: {undocumented}"


# --- §7.8: the no-Overleaf-code originality clause ---------------------------- #


def test_contributing_has_originality_clause() -> None:
    text = (_ROOT / "CONTRIBUTING.md").read_text("utf-8").lower()
    assert "no overleaf" in text or "no-overleaf" in text
    assert "agpl" in text and "mit" in text
    assert "original work" in text


# --- §7.9: internal links and anchors resolve -------------------------------- #


def _slug(heading: str) -> str:
    s = heading.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s)
    return s.replace(" ", "-")


def _markdown_files() -> list[Path]:
    files = [_ROOT / "README.md", _ROOT / "CONTRIBUTING.md"]
    files += sorted(_DOCS.rglob("*.md"))
    return files


def test_internal_links_resolve() -> None:
    broken: list[str] = []
    link_re = re.compile(r"\]\(([^)]+)\)")
    for md in _markdown_files():
        text = md.read_text("utf-8")
        for target in link_re.findall(text):
            target = target.strip()
            if target.startswith(("http://", "https://", "mailto:", "<")):
                continue
            path_part, _, anchor = target.partition("#")
            if path_part:
                dest = (md.parent / path_part).resolve()
                if not dest.exists():
                    broken.append(f"{md.relative_to(_ROOT)} -> {target} (missing path)")
                    continue
            else:
                dest = md  # same-file anchor
            if anchor and dest.suffix == ".md" and dest.is_file():
                slugs = {_slug(h) for h in _headings(dest.read_text("utf-8"))}
                if anchor not in slugs:
                    broken.append(f"{md.relative_to(_ROOT)} -> {target} (missing anchor)")
    assert broken == [], "broken internal links:\n" + "\n".join(broken)


# --- §7.6: the committed OpenAPI artifact is in sync -------------------------- #


def _load_export_module() -> object:
    spec = importlib.util.spec_from_file_location(
        "export_openapi", _ROOT / "backend" / "scripts" / "export_openapi.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_openapi_artifact_in_sync() -> None:
    committed = json.loads((_DOCS / "api" / "openapi.json").read_text("utf-8"))
    current = _load_export_module().generate_openapi()  # type: ignore[attr-defined]
    assert current == committed, (
        "docs/api/openapi.json is stale — run `python scripts/export_openapi.py` and commit it"
    )
