"""Export the FastAPI OpenAPI schema to docs/api/openapi.json (spec 58).

The schema is built from the real app factory, so the committed reference can
never drift from the routes/models — a fast test (tests/unit/test_docs.py) calls
``generate_openapi`` and asserts equality with the committed file.

    python scripts/export_openapi.py        # rewrite docs/api/openapi.json
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_OUTPUT = Path(__file__).resolve().parents[2] / "docs" / "api" / "openapi.json"


def generate_openapi() -> dict[str, Any]:
    """The OpenAPI schema for the current app (env-independent: title/version are
    static), normalized through JSON so it compares cleanly to the committed file."""
    from inkstave.app import create_app

    schema = create_app().openapi()
    return json.loads(json.dumps(schema))  # type: ignore[no-any-return]


def render() -> str:
    return json.dumps(generate_openapi(), indent=2, sort_keys=True) + "\n"


def main() -> int:
    _OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    _OUTPUT.write_text(render(), encoding="utf-8")
    print(f"wrote {_OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
