# Spec 121 — Git access to projects (prompt)

Give every project a Git URL: `git clone`, `pull` and `push` over Smart HTTP, authenticated with personal access
tokens. A fetch first snapshots the live project into a commit, and a push is applied to the project as live edits
that collaborators see at once. Read `spec.md`, then implement it with its tests.

Depends on 12–14, 28–31 (history), 101 (path rules), 109. Read `docs/system/projects.md`, `collab.md`,
`history.md` and `security.md` first. Write the ADR (library choice and sync model) before the code.
