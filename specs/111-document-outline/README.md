# Spec 111 — Document outline (prompt)

Give the editor an outline of the whole project: the sections of the main document and of every file it pulls
in with `\input` / `\include`, as a clickable tree that highlights where the cursor is. It also builds the
**project index** (sections and labels of every file) that spec 112 reuses for `\ref`. Read `spec.md`, then
implement it with its tests.

Depends on 18, 28, 107. Read the "Editor workspace" section of `docs/system/frontend.md` first.
