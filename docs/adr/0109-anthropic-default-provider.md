# ADR 0109 — The Anthropic API is the default LLM provider

**Status:** accepted · **Phase:** 7 — Hardening, packaging & docs

## Decision

The agent calls the Claude API through the official `anthropic` SDK by default, with
`claude-haiku-5-5`. `ANTHROPIC_API_KEY` is the only value a deployment has to set.

OpenRouter stays available with `AGENT_LLM_PROVIDER=openrouter`, which also needs
`OPENROUTER_API_KEY` and an `AGENT_MODEL` that provider knows. The graph still sees only the
`LLMClient` protocol, and `build_llm_client` is the one place that chooses.

## Consequences

- Upgrading a deployment that used OpenRouter needs `AGENT_LLM_PROVIDER=openrouter`, or a new
  key and the removal of its old `AGENT_MODEL`.
- `AGENT_TEMPERATURE` no longer applies by default, because Haiku 5.5 rejects sampling parameters.
- Haiku 5.5 thinks by default, so the assistant turn carries `provider_blocks` through the
  graph to send thinking back with tool results.
- `AGENT_MODEL_COST_TABLE` prices Haiku 5.5 at the rate for prompts up to 100K tokens; longer
  prompts cost five times more and are not modelled.
