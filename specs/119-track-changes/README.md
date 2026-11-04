# Spec 119 — Suggest changes (track changes) (prompt)

Let each member switch on **Suggesting**: while it is on, what they type and delete becomes a suggestion marked
in the text, with their name, that any editor accepts or rejects. Suggestions live in the same Yjs document as
the text, so they sync, persist and undo with it. Read `spec.md`, then implement it with its tests.

Depends on 28–30, 110 (decoration look), 118 (review column). Read `docs/system/collab.md` first. This is the
hardest spec of the series: do a spike on the CodeMirror ↔ Yjs recording path (§5.3) before the rest, and stop
to ask if `y-codemirror.next` cannot do it.
