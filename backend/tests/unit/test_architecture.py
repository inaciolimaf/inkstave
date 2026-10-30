"""Design rules no third-party lint covers (import-linter guards the import boundaries)."""

from __future__ import annotations

import ast
import re
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
QUERY_BUILDERS = {"select", "insert", "update", "delete"}
SQL_STATEMENT = re.compile(r"(SELECT|INSERT INTO|UPDATE|DELETE FROM|WITH RECURSIVE)\s")


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


def _relative(path: Path) -> str:
    return path.relative_to(PACKAGE).as_posix()


def _is_route_file(path: Path) -> bool:
    return path.name == "routes.py" or "routes" in path.parent.parts


def _is_model_file(path: Path) -> bool:
    return path.name == "models.py" or path.parent.name == "models"


def _docstrings(tree: ast.AST) -> set[int]:
    bodies = [n for n in ast.walk(tree) if isinstance(n, ast.Module | ast.ClassDef | ast.FunctionDef)]
    bodies += [n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)]
    return {
        id(node.body[0].value)
        for node in bodies
        if node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant)
    }


def _is_sql_call(call: ast.Call) -> bool:
    if isinstance(call.func, ast.Attribute):  # labels_service.delete(...) is not a query
        return call.func.attr in {"execute", "scalar", "scalars"}
    return _call_name(call) in QUERY_BUILDERS


def test_routes_hold_no_sql() -> None:
    offenders = [
        f"{_relative(path)}:{call.lineno}"
        for path in _source_files()
        if _is_route_file(path)
        for call in _calls(path)
        if _is_sql_call(call)
    ]
    assert offenders == []


def test_sql_only_through_the_query_builder() -> None:
    offenders = []
    for path in _source_files():
        for call in _calls(path):
            name = _call_name(call)
            if name == "exec_driver_sql" or (name == "text" and not _is_model_file(path)):
                offenders.append(f"{_relative(path)}:{call.lineno}")
    assert offenders == []


def test_no_sql_in_string_literals() -> None:
    offenders = []
    for path in _source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = _docstrings(tree)
        for node in ast.walk(tree):
            is_string = isinstance(node, ast.Constant) and isinstance(node.value, str)
            if is_string and id(node) not in docstrings and SQL_STATEMENT.match(node.value.strip()):
                offenders.append(f"{_relative(path)}:{node.lineno}")
    assert offenders == []


def test_no_synchronous_database_api() -> None:
    # A synchronous ORM call in an async def stops every request on the worker, and ruff cannot
    # see one. The migration runner is the listed exception: Alembic is synchronous, and the
    # app only calls it through asyncio.to_thread.
    offenders = []
    for path in _source_files():
        if _relative(path) == "modules/admin/provisioning/migrate.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("sqlalchemy"):
                names = {alias.name for alias in node.names}
                if names & {"Session", "create_engine", "sessionmaker"}:
                    offenders.append(f"{_relative(path)}:{node.lineno}")
    assert offenders == []


def test_ownership_is_never_checked_by_hand() -> None:
    offenders = []
    for path in _source_files():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Compare)
                and isinstance(node.left, ast.Attribute)
                and node.left.attr == "user_id"
                and isinstance(node.ops[0], ast.NotEq)
            ):
                offenders.append(f"{_relative(path)}:{node.lineno}")
    assert offenders == []


def test_no_comment_separators() -> None:
    separator = re.compile(r"^\s*#\s*(---|[-=]{5,})")
    offenders = [
        f"{_relative(path)}:{number}"
        for path in _source_files()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if separator.match(line)
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
