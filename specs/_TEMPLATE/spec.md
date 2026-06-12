<!--
  CANONICAL TEMPLATE for spec.md — the detailed requirements of one spec.
  Every spec.md MUST contain all the sections below, in this order.
  Be as detailed and unambiguous as possible: a competent engineer (or agent)
  should be able to implement the spec without guessing. Replace <PLACEHOLDERS>.
-->

# Spec NN — <Human Title> (requirements)

## 1. Summary
<2–4 sentences: what this spec delivers and why it exists in this position.>

## 2. Context & dependencies
- **Depends on:** specs <NN, …> (what they provide that this spec builds on).
- **Unlocks:** specs <NN, …> (what later work relies on this).
- **Affected areas:** <backend / frontend / collab / infra / docs>.

## 3. Goals
- <bullet list of concrete, testable goals>

## 4. Non-goals (explicitly out of scope)
- <things a reader might expect but that belong elsewhere / later>

## 5. Detailed requirements

### 5.1 Data model (if any)
<Tables/entities, columns with types, constraints, indexes, relationships.
Include the Alembic migration expectations. Use precise types.>

### 5.2 Backend / API (if any)
<Every endpoint: method, path, auth requirement, request schema (Pydantic),
response schema, status codes, error cases. Or service/module contracts,
function signatures, job definitions.>

### 5.3 Frontend / UI (if any)
<Routes, components (prefer shadcn/ui), states, user interactions, validation,
loading/error/empty states, accessibility notes.>

### 5.4 Real-time / jobs / external integrations (if any)
<WebSocket messages, ARQ job signatures, LLM calls, Tectonic invocation, etc.>

### 5.5 Configuration
<New env vars (added to .env.example), config files, feature flags, defaults.>

## 6. Overleaf reference (study only — never copy)
> Read these in `../overleaf/` to understand the approach. Inkstave code must be
> written independently. If a capability has no Overleaf equivalent, say so.

- `path/in/overleaf` — <what to learn from it>
- …

## 7. Acceptance criteria
<Given/When/Then style, numbered, each independently verifiable.>
1. …

## 8. Test plan
> All tests combined across the project must keep the suite under 2 minutes.
> Slow work (LaTeX, real LLM) must be stubbed here and exercised only in async jobs.

- **Unit (pytest / Vitest):** <what to cover>
- **Integration (pytest + httpx / test DB / fake Redis):** <what to cover>
- **E2E (Playwright):** <user-visible flow to cover, if applicable at this stage>
- **Performance/budget note:** <how this spec keeps tests fast>

## 9. Definition of Done
- [ ] All requirements in §5 implemented.
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green.
- [ ] Full suite runs in < 2 minutes.
- [ ] Lint/format/type-check clean.
- [ ] New env vars documented in `.env.example`; docs updated if needed.
- [ ] No Overleaf code copied.
