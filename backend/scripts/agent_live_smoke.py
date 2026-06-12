"""Manual live smoke for the OpenRouter LLM client (spec 67).

Runs ONE tiny real completion through the real ``OpenRouterLLMClient`` — only when
``OPENROUTER_API_KEY`` is set. Never run in CI or the fast test suite (it makes a
real network call). If the key is absent it prints a message and exits 0 (skip),
so wiring it into a release checklist never fails the build.

    just agent-live      # or: uv run --project backend python scripts/agent_live_smoke.py
"""

from __future__ import annotations

import asyncio
import os
import sys


async def _run() -> int:
    from inkstave.agent.llm.base import LLMMessage
    from inkstave.agent.llm.openrouter import OpenRouterLLMClient
    from inkstave.agent.settings import get_agent_settings

    client = OpenRouterLLMClient(get_agent_settings())
    print(f"Calling {client.model} via OpenRouter…")
    resp = await client.complete(
        [LLMMessage(role="user", content="Reply with the single word: ok")],
        max_tokens=8,
    )
    print(f"  content: {resp.content!r}")
    print(f"  finish_reason: {resp.finish_reason}  usage.total: {resp.usage.total}")
    if not resp.content:
        print("FAIL: empty completion content", file=sys.stderr)
        return 1
    print("PASS: live OpenRouter completion succeeded")
    return 0


def main() -> int:
    if not os.getenv("OPENROUTER_API_KEY"):
        print("OPENROUTER_API_KEY not set — skipping live smoke (this is fine in CI).")
        return 0
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
