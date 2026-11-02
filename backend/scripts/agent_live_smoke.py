"""Manual live smoke for the configured LLM client (spec 67).

Runs ONE tiny real completion through the real client — only when the key of
``AGENT_LLM_PROVIDER`` is set. Never run in CI or the fast test suite (it makes a
real network call). If the key is absent it prints a message and exits 0 (skip),
so wiring it into a release checklist never fails the build.

    just agent-live      # or: uv run --project backend python scripts/agent_live_smoke.py
"""

from __future__ import annotations

import asyncio
import sys


async def _run() -> int:
    from inkstave.core.config.agent import get_agent_settings
    from inkstave.modules.agent.llm.base import LLMMessage
    from inkstave.modules.agent.llm.factory import build_llm_client

    settings = get_agent_settings()
    client = build_llm_client(settings)
    print(f"Calling {client.model} via {settings.agent_llm_provider}…")
    resp = await client.complete(
        [LLMMessage(role="user", content="Reply with the single word: ok")],
        max_tokens=1024,  # Haiku 5.5 thinks by default, and thinking counts toward this cap
    )
    print(f"  content: {resp.content!r}")
    print(f"  finish_reason: {resp.finish_reason}  usage.total: {resp.usage.total}")
    if not resp.content:
        print("FAIL: empty completion content", file=sys.stderr)
        return 1
    print("PASS: live completion succeeded")
    return 0


def main() -> int:
    from inkstave.core.config.agent import get_agent_settings

    settings = get_agent_settings()
    uses_openrouter = settings.agent_llm_provider == "openrouter"
    if not (settings.openrouter_api_key if uses_openrouter else settings.anthropic_api_key):
        print("No API key for the configured provider — skipping live smoke (this is fine in CI).")
        return 0
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
