"""Design rules no third-party lint covers (import-linter guards the import boundaries)."""

from __future__ import annotations

import ast
import subprocess
import sys
import tomllib
from collections import Counter
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
PACKAGE = BACKEND / "src" / "inkstave"
MODULES = sorted(p.name for p in (PACKAGE / "modules").iterdir() if (p / "__init__.py").exists())
MAX_FILES_PER_FOLDER = 8
GENERIC_FOLDERS = {"services", "utils", "helpers", "common", "misc"}
# Only ever lowers: each exception is a cycle to resolve (see the "Target:" comments).
MAX_IMPORT_EXCEPTIONS = 3


def _source_files() -> list[Path]:
    return [p for p in PACKAGE.rglob("*.py") if "__pycache__" not in p.parts]


def _call_name(node: ast.Call) -> str:
    return node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")


def _calls(path: Path) -> list[ast.Call]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [node for node in ast.walk(tree) if isinstance(node, ast.Call)]


def test_session_dependency_is_only_reached_through_the_unit_of_work() -> None:
    # A bare Depends(get_db_session) commits after the response and opens a second session.
    offenders = [
        f"{path.relative_to(PACKAGE)}:{call.lineno}"
        for path in _source_files()
        if path.relative_to(PACKAGE).as_posix() != "core/db/session.py"
        for call in _calls(path)
        if _call_name(call) == "Depends" and "get_db_session" in ast.unparse(call)
    ]
    assert offenders == []


def test_no_folder_holds_more_than_eight_files() -> None:
    sizes = Counter(p.parent for p in _source_files() if p.name != "__init__.py")
    crowded = {str(folder): n for folder, n in sizes.items() if n > MAX_FILES_PER_FOLDER}
    assert crowded == {}


def test_no_generic_technical_folder() -> None:
    folders = {part for p in _source_files() for part in p.relative_to(PACKAGE).parts[:-1]}
    assert folders & GENERIC_FOLDERS == set()


def test_every_module_declares_its_public_interface() -> None:
    for name in MODULES:
        assert "__all__" in (PACKAGE / "modules" / name / "__init__.py").read_text(encoding="utf-8"), name


def test_import_exceptions_only_go_down() -> None:
    config = tomllib.loads((BACKEND / "pyproject.toml").read_text(encoding="utf-8"))
    contracts = config["tool"]["importlinter"]["contracts"]
    assert sum(len(c.get("ignore_imports", [])) for c in contracts) <= MAX_IMPORT_EXCEPTIONS


@pytest.mark.parametrize("name", MODULES)
def test_module_imports_first_in_a_fresh_interpreter(name: str) -> None:
    # Cycles between modules only break for one import order, which the app and the suite
    # never exercise: they load everything in the same sequence.
    env = {"JWT_SECRET": "x" * 40, "PATH": "/usr/bin:/bin"}
    code = f"import inkstave.modules.{name}"
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, env=env, check=False)
    assert done.returncode == 0, done.stderr.decode()


@pytest.mark.parametrize(
    "code",
    [
        "from inkstave.main import app",
        "from inkstave.compile.worker import WorkerSettings",
        "from inkstave.cli import main",
    ],
)
def test_deployment_entrypoints_resolve(code: str) -> None:
    # Dockerfile, compose files and [project.scripts] name these paths.
    env = {"JWT_SECRET": "x" * 40, "PATH": "/usr/bin:/bin"}
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, env=env, check=False)
    assert done.returncode == 0, done.stderr.decode()
