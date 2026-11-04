"""Importing an Overleaf template (spec 120): the report, the template fixes and the first compile.

The archives are tiny and written here to mimic an Overleaf export's layout. Nothing is fetched
from overleaf.com, and the compile is a fake hook, so no Tectonic runs.
"""

from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.infra.storage.base import ObjectStore
from tests.fixtures.paths import REPO_ROOT
from tests.integration._project_import_support import (
    FakeFirstCompile,
    FakeImportEnqueuer,
    auth,
    flatten,
    install_enqueuer,
    install_store,
    make_zip,
    post_import,
    run_job,
)

pytestmark = pytest.mark.integration

IMPORT_PATH_FILES = [
    *sorted((REPO_ROOT / "backend/src/inkstave/modules/projects/transfer").rglob("*.py")),
    REPO_ROOT / "backend/src/inkstave/modules/projects/routes/project_import.py",
]

# An Overleaf-shaped template: a title, an EPS figure, an input, a bibliography and a latexmkrc.
OVERLEAF_TEMPLATE = {
    "main.tex": (
        b"\\documentclass{article}\n"
        b"\\title{Journal of Things}\n"
        b"\\begin{document}\n"
        b"\\includegraphics[width=3cm]{figures/plot.eps}\n"
        b"\\input{sections/intro}\n"
        b"\\end{document}\n"
    ),
    "sections/intro.tex": b"Intro text.\n",
    "refs.bib": b"@book{x, title={T}}\n",
    "figures/plot.eps": b"%!PS-Adobe-3.0 EPSF-3.0\n%%BoundingBox: 0 0 10 10\n",
    "latexmkrc": b"$pdf_mode = 1;\n",
}


@pytest_asyncio.fixture(autouse=True)
async def store(app: Any) -> ObjectStore:
    """Every test here imports through a fake store and a fake enqueuer: no Redis, no bytes on disk."""
    return install_store(app)


@pytest.fixture(autouse=True)
def enqueuer(app: Any) -> FakeImportEnqueuer:
    return install_enqueuer(app)


@pytest.fixture
def first_compile() -> FakeFirstCompile:
    return FakeFirstCompile()


async def _import(
    client: AsyncClient,
    db_session: AsyncSession,
    store: ObjectStore,
    redis: Any,
    entries: dict[str, bytes],
    first_compile: FakeFirstCompile | None = None,
    *,
    source: str | None = "overleaf_template",
    name: str | None = None,
) -> tuple[dict[str, str], dict[str, Any], dict[str, Any]]:
    headers = await auth(db_session)
    body = (await post_import(client, headers, make_zip(entries), source=source, name=name)).json()
    await run_job(db_session, store, redis, body["import_id"], first_compile)
    row = (
        await client.get(f"/api/v1/projects/{body['project_id']}/import/{body['import_id']}", headers=headers)
    ).json()
    tree = (await client.get(f"/api/v1/projects/{body['project_id']}/tree", headers=headers)).json()
    return headers, row, flatten(tree["root"])


def _findings(row: dict[str, Any]) -> list[tuple[str, str, int]]:
    return [(f["rule_id"], f["path"], f["line"]) for f in row["compat_report"]]


async def test_overleaf_zip_keeps_eps(
    async_client: AsyncClient, db_session: AsyncSession, store: ObjectStore, redis: Any
) -> None:
    _, row, nodes = await _import(async_client, db_session, store, redis, OVERLEAF_TEMPLATE)

    assert row["status"] == "success"
    assert row["source"] == "overleaf_template"
    assert nodes["figures/plot.eps"]["type"] == "file"
    assert nodes["latexmkrc"]["type"] == "doc"
    rule_ids = {finding[0] for finding in _findings(row)}
    assert {"latexmkrc", "eps_figure"} <= rule_ids
    assert row["report_seen_at"] is None


async def test_template_name_comes_from_the_title(
    async_client: AsyncClient, db_session: AsyncSession, store: ObjectStore, redis: Any
) -> None:
    headers, _, _ = await _import(async_client, db_session, store, redis, OVERLEAF_TEMPLATE)
    projects = (await async_client.get("/api/v1/projects", headers=headers)).json()["items"]
    assert [p["name"] for p in projects] == ["Journal of Things"]


async def test_explicit_name_wins_over_the_title(
    async_client: AsyncClient, db_session: AsyncSession, store: ObjectStore, redis: Any
) -> None:
    headers, _, _ = await _import(async_client, db_session, store, redis, OVERLEAF_TEMPLATE, name="My paper")
    projects = (await async_client.get("/api/v1/projects", headers=headers)).json()["items"]
    assert [p["name"] for p in projects] == ["My paper"]


async def test_case_clash_renames_second(
    async_client: AsyncClient, db_session: AsyncSession, store: ObjectStore, redis: Any
) -> None:
    entries = {
        "main.tex": b"\\documentclass{article}\n",
        "Intro.tex": b"first\n",
        "intro.tex": b"second\n",
    }
    _, row, nodes = await _import(async_client, db_session, store, redis, entries)

    assert row["status"] == "success"
    assert row["entries_imported"] == row["entries_total"] == 3
    assert nodes["Intro.tex"]["type"] == "doc"
    assert nodes["intro (2).tex"]["type"] == "doc"


async def test_reserved_device_name_is_renamed_for_a_template(
    async_client: AsyncClient, db_session: AsyncSession, store: ObjectStore, redis: Any
) -> None:
    entries = {"main.tex": b"\\documentclass{article}\n", "con.tex": b"text\n"}
    _, row, nodes = await _import(async_client, db_session, store, redis, entries)

    assert row["status"] == "success"
    assert nodes["con_.tex"]["type"] == "doc"


async def test_minted_reports_shell_escape_at_the_line(
    async_client: AsyncClient, db_session: AsyncSession, store: ObjectStore, redis: Any
) -> None:
    entries = {
        "main.tex": b"\\documentclass{article}\n\\usepackage{graphicx}\n\\usepackage[cache]{minted}\n",
    }
    _, row, _ = await _import(async_client, db_session, store, redis, entries)

    assert _findings(row) == [("shell_escape", "main.tex", 3)]


async def test_missing_include_is_reported(
    async_client: AsyncClient, db_session: AsyncSession, store: ObjectStore, redis: Any
) -> None:
    entries = {"main.tex": b"\\documentclass{article}\n\\input{chapters/gone}\n"}
    _, row, _ = await _import(async_client, db_session, store, redis, entries)

    assert _findings(row) == [("missing_file", "main.tex", 2)]


async def test_plain_zip_gets_no_report_and_no_compile(
    async_client: AsyncClient, db_session: AsyncSession, store: ObjectStore, redis: Any
) -> None:
    hook = FakeFirstCompile()
    _, row, nodes = await _import(
        async_client, db_session, store, redis, OVERLEAF_TEMPLATE, hook, source=None
    )

    assert row["source"] == "zip"
    assert row["compat_report"] is None
    assert hook.calls == []
    assert nodes["main.tex"]["type"] == "doc"


async def test_template_starts_its_first_compile_as_the_requester(
    async_client: AsyncClient, db_session: AsyncSession, store: ObjectStore, redis: Any
) -> None:
    hook = FakeFirstCompile()
    _, row, _ = await _import(async_client, db_session, store, redis, OVERLEAF_TEMPLATE, hook)

    assert len(hook.calls) == 1
    project_id, requester, main_file = hook.calls[0]
    assert str(project_id) == row["project_id"]
    assert main_file == "main.tex"
    assert requester is not None


async def test_failed_template_import_starts_no_compile(
    async_client: AsyncClient, db_session: AsyncSession, store: ObjectStore, redis: Any
) -> None:
    hook = FakeFirstCompile()
    entries = {"../escape.tex": b"x", "main.tex": b"y"}
    _, row, _ = await _import(async_client, db_session, store, redis, entries, hook)

    assert row["status"] == "failure"
    assert hook.calls == []


async def test_report_seen_is_stamped_once(
    async_client: AsyncClient, db_session: AsyncSession, store: ObjectStore, redis: Any
) -> None:
    headers, row, _ = await _import(async_client, db_session, store, redis, OVERLEAF_TEMPLATE)
    url = f"/api/v1/projects/{row['project_id']}/import/{row['import_id']}/report-seen"

    first = await async_client.post(url, headers=headers)
    assert first.status_code == 204
    seen = (await async_client.get(url.rsplit("/", 1)[0], headers=headers)).json()["report_seen_at"]
    assert seen is not None

    assert (await async_client.post(url, headers=headers)).status_code == 204
    again = (await async_client.get(url.rsplit("/", 1)[0], headers=headers)).json()["report_seen_at"]
    assert again == seen


async def test_report_seen_is_hidden_from_other_users(
    async_client: AsyncClient, db_session: AsyncSession, store: ObjectStore, redis: Any
) -> None:
    _, row, _ = await _import(async_client, db_session, store, redis, OVERLEAF_TEMPLATE)
    stranger = await auth(db_session)
    url = f"/api/v1/projects/{row['project_id']}/import/{row['import_id']}/report-seen"

    assert (await async_client.post(url, headers=stranger)).status_code == 404


async def test_unknown_source_is_refused(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: FakeImportEnqueuer
) -> None:
    headers = await auth(db_session)
    response = await post_import(async_client, headers, make_zip({"a.tex": b"x"}), source="github")
    assert response.status_code == 422
    assert enqueuer.calls == []


async def test_template_import_makes_no_http_request() -> None:
    """Inkstave never contacts overleaf.com: no HTTP client is imported on the import path."""
    forbidden = ("import httpx", "import requests", "import urllib", "import aiohttp", "overleaf.com")
    for path in IMPORT_PATH_FILES:
        text = path.read_text(encoding="utf-8")
        for needle in forbidden:
            assert needle not in text, f"{path.name} mentions {needle!r}"
