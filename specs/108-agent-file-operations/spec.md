# Spec 108 — Agent file operations and images (requirements)

## 1. Summary
The agent could read, search and propose edits to documents that already exist. It now also looks at
images and proposes creating, deleting, renaming and moving tree entities. Each proposal waits for the
user, who applies or rejects it from a card in the chat.

## 2. Context & dependencies
- **Depends on:** specs 12 (tree), 14 (files), 42 (tools), 43 (diffs), 44 (streaming), 46 (panel).
- **Affected areas:** backend, frontend, docs. Decision record: ADR 0110.

## 3. Goals
- `view_image` shows the model a PNG, JPEG, GIF or WebP from the project.
- `propose_create`, `propose_delete` and `propose_move` stage a proposal and change nothing.
- The user applies or rejects each proposal; a delete asks for confirmation.

## 4. Non-goals
- Creating or editing binary files. Viewing PDF, EPS or SVG figures.
- Applying several proposals at once.

## 5. Rules and guarantees
| Rule | Guarantee |
|---|---|
| A proposal changes nothing until applied | `test_a_proposal_changes_nothing_until_the_user_applies` |
| Applying needs the caller's own write access, checked at that moment | `test_a_viewer_cannot_apply` |
| A delete covers what the user saw; a folder that changed is refused | `test_delete_is_refused_when_the_folder_gained_a_file` |
| A decided proposal cannot run twice | `test_delete_and_move_apply_and_cannot_apply_twice` |
| Image bytes reach the model and are never stored | `test_the_model_gets_the_image_and_the_transcript_does_not` |
| The image type comes from the bytes, not the upload's declared type | `test_sniff_image` |

## 6. Acceptance criteria
- [x] All four tools are in `default_registry`.
- [x] Images reach the model through both LLM clients, Anthropic and OpenRouter.
- [x] A proposal survives a reload and shows its decided state.
- [x] Interface text exists in English and Portuguese.

## 7. Definition of Done
Tests above pass, `make lint types docs` passes, `docs/system/agent.md` describes the behavior.
