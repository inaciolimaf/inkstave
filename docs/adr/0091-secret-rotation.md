# ADR 0091 — Rotate the exposed OpenRouter key & guard against secret commits

**Status:** accepted (spec 91) · **Phase:** 9 — Hardening / secret hygiene

## Context

A code-smell audit found a **real, live OpenRouter API key** (pattern
`sk-or-v1-…`) sitting in the developer's local `.env`, duplicated on the
`openai_api_key=` and `OPENROUTER_API_KEY=` lines.

The `.env` file is correctly gitignored and was **never committed**, so there is
**no git-history exposure to purge** — this is a working-tree leak risk, not a
public exposure. But a live credential in any working tree is a standing hazard
(accidental paste, screen share, backup, `git add -f`), and the key has already
been seen by tooling. It must therefore be treated as **compromised**, and the
repository must gain an automated guard so no secret — or `.env` file — can ever
be committed.

This finding has **no Overleaf equivalent**; the response is implemented from the
spec alone. The change is **config + docs only**: no application behaviour
changes.

## Decision

1. **Rotate the key.** The OpenRouter key previously present in the local `.env`
   **must be rotated**: revoke the old key in the OpenRouter dashboard and issue a
   new one. Treat the old value as compromised regardless of it never being
   committed.
2. **New key never enters the repo.** The replacement key goes **only** into the
   developer's local, gitignored `.env` (and into deployment secret stores — e.g.
   the CI/CD secret manager). It is never written into any tracked file, commit
   message, ADR, or test fixture.
3. **`.env` is never committed.** `.env` (and any `*.env`) stays gitignored;
   `.env.example` carries **placeholders only** — every secret-shaped value after
   an `=` there must be empty or an obvious dummy.
4. **Automated guard.** A commit-time secret-scan runs via
   `.pre-commit-config.yaml` (spec 91): a `pygrep` hook rejects staged content
   containing API-key-shaped tokens (`sk-or-v1-…`, generic `sk-…`), and a second
   hook refuses to stage any `.env`/`*.env` file other than `.env.example`. The
   `.gitignore` `.env` rules carry an inline note so a future edit does not
   silently weaken them.

## Consequences

- The old credential is dead once rotated; the working-tree leak risk is closed.
- Accidental commits of a key or a `.env` file are blocked at commit time, on the
  staged diff, with a clear message — offline, with no external scanner to pull.
- Rotation itself is a **human action** this ADR mandates; the repo change cannot
  perform it. No code change and no history rewrite are required (the key was
  never committed).
- The real key value is reproduced **nowhere** in the repository — not here, not
  in `.env.example`, not in the hook config. Only obvious `…`/`TESTDUMMY`-style
  placeholders appear in docs and tests.
