# Spec 109 — Shared projects on the dashboard (prompt)

A collaborator who accepts an invite never sees the project in their list: `GET /projects` filters on
`owner_id`. Make the dashboard list every project the user is an active member of, with filters for all,
owned and shared, the owner's name, and the actions each role is allowed. Read `spec.md`, then implement it
with its tests.

Depends on 11, 16, 33. Read `docs/system/projects.md` and `docs/system/sharing.md` first.
