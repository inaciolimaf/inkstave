# ADR 0108 — Every connection has a deadline

**Status:** accepted · **Phase:** 7 — Hardening, packaging & docs

## Decision

The application engine sets `lock_timeout` (10 s), `statement_timeout` (30 s) and
`idle_in_transaction_session_timeout` (120 s) on every connection, through asyncpg's
`server_settings`. Redis, SMTP and S3 clients have explicit timeouts too. Each value is a
setting with a safe default; 0 turns a database limit off.

A transaction that must exceed a limit raises it for itself with `allow_idle` or
`allow_long_statements`, which are `SET LOCAL` through the query builder, and never globally.

## What the audit found

| Flow | Before | Now |
| --- | --- | --- |
| SSE and download streams | The request session stayed open for the whole stream, holding a transaction and a pooled connection | The unit of work closes before the body starts; streams read first or open a short session |
| Compile job | Read the sources, then sat idle in that transaction while Tectonic ran | Commits after assembly (`on_assembled`), so Tectonic runs with no transaction and no connection |
| Agent turn | One transaction across every model call, up to `AGENT_JOB_TIMEOUT_S` | Kept, because a failed turn must leave no messages behind; raises its idle limit with `allow_idle` |
| Account deletion | Cascades through every owned project's history | `allow_long_statements`, 5 minutes |
| Project import, history compaction | Statements are short, but S3 calls happen inside the transaction | Unchanged: each gap is bounded by the S3 timeouts, below the idle limit |
| Retention sweep | Bounded batches | Unchanged |
| Migrations | `env.py` and the advisory-lock connection build their own engines | Unchanged, and tested: they inherit none of these limits, so a long `ALTER` or a wait on the startup lock is never killed |

## Pitfall: Redis pub/sub

`socket_timeout` also applies to `PubSub.listen()`, which would raise on any channel quiet
for longer than the timeout and silently stop relaying collaboration updates between
instances. The bridge now polls `get_message` with a shorter timeout.
