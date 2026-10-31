# 107 — Editor focus layout

This changes spec 106 §7 (Editor) and spec 46 §5.4 (a docked, resizable agent panel). Three equal columns and
stacked rows of tools gave the screen no dominant element, and the modal agent hid the text it was
talking about.

## 1. Rules

| Rule | Guarantee |
|---|---|
| The text and the PDF are always on screen at desktop width | `Panes` in `frontend/src/modules/editor/workspace-panes.tsx` |
| One bar. History, download and the way back live in its menu | `frontend/src/modules/editor/editor-bar.test.tsx` |
| Compile is the bar's one solid action | `compileSlot` of `PreviewPane` |
| The file list opens over the text and closes on picking a file | `frontend/src/modules/editor/file-drawer.test.tsx` |
| Under the open drawer the text cannot be edited | `inert` in `frontend/src/modules/editor/content-pane.tsx` |
| A project opens on a document | `frontend/src/modules/editor/start-document.test.ts` |
| The agent window blocks nothing behind it and folds into a button | `frontend/src/modules/agent/AgentPanel.test.tsx` |
| Selected text offers the agent, and travels with the next message | `frontend/src/modules/editor/ask-agent-button.test.tsx`, `frontend/src/modules/agent/quote.test.ts` |
| A failed compile keeps the last PDF on screen, with a notice | `PreviewBody` |
| Warnings fold under the errors in the status line | `foldQuiet` of `ProblemsPanel` |
| A run's tool calls read as one line, in plain words | `frontend/src/modules/agent/transcript.test.tsx` |

## 2. Phone

One thing at a time, with the switch under the thumb: tabs for Content, Preview and Agent. Both panes stay
mounted. A successful compile moves to the PDF, and following a problem or a PDF click moves to the text. The
agent is a full-height sheet between the bar and the tabs. The file drawer works as on the desktop. "Ask the
agent" sits in a fixed spot over the tabs, because the system's selection menu takes the space above the text.

## 3. Out of this spec

Reviewing the agent's changes inside the text was on the demo and is not built: review still opens
`DiffReviewDialog`. It is recorded in `docs/known-gaps.md`.
