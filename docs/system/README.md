# System documentation

How Inkstave works **today**, one file per domain, written from the code. `specs/` records what was
asked and why, and `docs/adr/` records past decisions as history; when they disagree with the code,
the code wins and the domain file says so under "Points of attention".

Domain names come from [`docs/glossary.md`](../glossary.md). What is knowingly unfinished is listed in
[`docs/known-gaps.md`](../known-gaps.md).

## Index

| File | Domain | Specs |
|---|---|---|
| [overview.md](overview.md) | Architecture, lifecycle, settings, errors, database, migrations, CLI, domain map | 01–05, 53, 56, 57, 62, 63 |
| [auth.md](auth.md) | Accounts, sessions, `session_version`, `revoked_sessions`, login limits, e-mail link flows, admin setup | 06–08, 10, 59, 63, 92, 104 |
| [projects.md](projects.md) | Projects, file tree, zip import and export | 11, 12, 15, 95, 101, 102 |
| [documents.md](documents.md) | Document content, autosave contract, binary files, object storage | 13, 14, 19 |
| [compile.md](compile.md) | Compile queue, runners and sandbox, outputs, SyncTeX, log parsing | 21–23, 25–27, 105 |
| [collab.md](collab.md) | CRDT documents, rooms, the collaboration WebSocket, presence | 28–30, 65, 66, 74 |
| [sharing.md](sharing.md) | Collaborators, invites, roles, authorization | 33–35 |
| [discussion.md](discussion.md) | Project chat, the project event stream | 117 |
| [history.md](history.md) | Version capture, compaction, diffs, labels, restore | 36–38, 40 |
| [notifications.md](notifications.md) | Inbox, e-mail rendering and delivery | 39, 103 |
| [agent.md](agent.md) | AI agent: graph, tools, diffs, streaming, safety | 41–50, 67, 108 |
| [observability.md](observability.md) | Logs, metrics, tracing, health and readiness | 51 |
| [security.md](security.md) | Threat model, headers, limits, secrets, proxy trust | 52, 55, 91 |
| [frontend.md](frontend.md) | Stack, routes, API client, modules, i18n, tests | 09, 16–18, 24, 31, 32, 38, 46, 47, 61, 64 |

## Template

A section that does not apply is dropped. Each file runs 100–300 lines, a little more for the widest
domains, and describes what the code does.

```markdown
# <Domain>
One paragraph: what it is for whoever uses it and the spec it came from.
## Where it is         table File | Role (backend, frontend, tests)
## Data                tables and the migration that created them; files on disk; cache
## Routes              table Method and path | What it does | Errors (error envelope code)
## How it works        main flows, in order, with function names
## Rules and guarantees each invariant and the test that guarantees it (backend/tests/x.py::name)
## Settings            the domain's environment variables
## Points of attention pitfalls, non-obvious decisions, divergences from the spec
```

## Update rule

The system changed, the documentation changes, in the same commit: a route, table, flow, rule,
environment variable or a new, removed or renamed file updates the domain's file here. A new domain gets
a new file and a line in the index. A new domain term gets a line in the glossary.

`make docs` guarantees two things, configured in `[tool.docs-coverage]` of `backend/pyproject.toml`:

- **DOC001**: every module, infra and core package and frontend route is cited between backticks here;
- **DOC002**: every repository path cited between backticks exists, and every `path.py::name` points to
  a real `def name`.

Paths are root-relative (`backend/src/inkstave/...`, `frontend/src/...`). Identifiers appear exactly as in
the code. Product text quoted here stays in the product's language.
