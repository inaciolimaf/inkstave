# Spec 42 — Agent Tools (search / read / list / locate / propose)

**Type:** 🟢 feature  ·  **Phase:** AI writing agent  ·  **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements are in
   [`spec.md`](spec.md). Implement *exactly* what it describes — no more, no less.
   If something is ambiguous, prefer the simplest option consistent with
   `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** Depends on: **41** (the LangGraph scaffold, State,
   `AgentDeps`, `LLMClient`/`FakeLLM`, tool-registry hook, sessions/messages),
   **12** (file-tree model: folders/docs/files, paths, ids), **13** (document
   content storage & CRUD). They must be implemented and green.
3. **Study the Overleaf reference (for understanding only).** **There is none for
   the agent** — Overleaf has no AI agent and no tool abstraction. The *only*
   thing to study is Inkstave's **own** specs 12 and 13, because the read/search
   tools call those models/services. Do not copy Overleaf code.
4. **Implement** the typed tool set, the tool registry that plugs into the
   spec-41 graph, per-tool input/output schemas, error handling, and project-scoped
   authorization.
5. **Write the tests** listed in the Test plan. The LLM is always the injected
   `FakeLLM`; tools run against a seeded test project/database.
6. **Verify.** Full suite passes and stays under the 2-minute budget. Check every
   Acceptance criterion and Definition-of-Done item.
7. **Record decisions.** Add a short ADR if you make a notable design choice
   (e.g. the section-locator heuristic).

When all Definition-of-Done items pass, this spec is complete. Move to spec 43.

## One-line goal

The agent gains a registry of typed, project-scoped **tools** — `search_project`,
`read_file`, `list_tree`, `locate_section`, and `propose_edit` — that the
spec-41 LangGraph agent can call to inspect a project and **stage** (not apply)
proposed changes.

## Do NOT (scope guard)

- Do not generate or store **unified diffs / `proposed_diffs`** — `propose_edit`
  only *stages* an intent; diff computation and storage are spec 43.
- Do not build the **HTTP API / streaming / ARQ** — spec 44.
- Do not build the **rich LaTeX parser** — `locate_section` is a basic heuristic
  here; spec 48 supplies the richer parser.
- Do not write to documents directly, ever. Tools are read-only except
  `propose_edit`, which only stages an intent in agent state.
- Do not build any frontend (46/47).
- Do not copy Overleaf source code (there is none for the agent).
