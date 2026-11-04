# Spec 122 — Project search and replace (prompt)

Give the editor a search over every document of the project at once, with match case, whole word and regular
expression options, results grouped by file, a click that opens the match, and replace one or replace all. A
replace writes through the collaboration channel, so it lands on the live text and every collaborator sees it.
Read `spec.md`, then implement it with its tests.

Depends on 31, 47, 111. Read the "Editor workspace" and "Agent and diff review" sections of
`docs/system/frontend.md` first.
