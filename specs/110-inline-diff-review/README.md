# Spec 110 — Review the agent's changes inside the text (prompt)

The agent's proposals are reviewed in `DiffReviewDialog`, away from the text. The spec 107 demo showed them
in the editor instead. Replace the dialog with inline review: removed text in red, added text in green, accept
or reject per hunk in place, and record the outcome on the server so an applied proposal no longer comes back
after a reload. Read `spec.md`, then implement it with its tests.

Depends on 43, 47, 75, 107. Read `docs/system/agent.md` and the "Agent and diff review" section of
`docs/system/frontend.md` first.
