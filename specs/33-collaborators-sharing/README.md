# Spec 33 — Collaborators & sharing

**Type:** 🟢 feature  ·  **Phase:** Real-time collaboration  ·  **Status:** ☑ done

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on: **11** (project model & CRUD,
   project ownership) and **32** (presence — collaborators editing live). It also
   assumes **06** (user model), **08** (current-user dependency) and **03**
   (async SQLAlchemy + Alembic) exist with passing tests.
3. **Study the Overleaf reference (for understanding only).** Read the paths in
   the "Overleaf reference" section of `spec.md` inside the cloned repo at
   `../overleaf/`. **Do not copy or translate any Overleaf code** — it is AGPLv3
   and Inkstave is MIT. Learn the *sharing model* (invites by email, roles,
   accept/decline, ownership transfer), then implement independently.
4. **Implement** the backend (membership + invite models, migrations, the
   `/members` and `/invites` endpoints, an async-stubbed invite-email hook) and
   the frontend "Share" modal (shadcn/ui).
5. **Write the tests** listed in the spec's Test plan (pytest unit + integration;
   Vitest for the modal). No heavy e2e required here.
6. **Verify.** Run the full test suite (< 2 min). Check every Acceptance
   criterion and Definition-of-Done item.
7. **Record decisions.** If you made an architectural decision (e.g. invite
   token format, single-role-per-user), add a short note under `docs/`.

When all Definition-of-Done items pass, this spec is complete. Move to spec 34.

## One-line goal

A project owner can invite people by email with a role (owner/editor/viewer),
invitees can accept or decline, and owners can list, change-role, remove, leave,
or transfer ownership of a project — all backed by membership and invite tables.

## Do NOT (scope guard)

- Do not implement *enforcement* of roles across REST/WebSocket/compile — that is
  spec 34. This spec stores roles and exposes the membership API/UI; the
  consistent guard layer comes next. (You may add the minimal owner-only checks
  needed to protect the sharing endpoints themselves.)
- Do not send real emails — the invite email is an **async ARQ job stub** here;
  real email delivery is spec 39.
- Do not build in-app notifications — spec 39.
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
