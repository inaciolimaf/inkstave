# Inkstave — User Guide

A task-oriented tour of Inkstave, the real-time collaborative LaTeX editor with a
built-in AI writing agent. See the [docs index](README.md) for everything else.

## Account

1. Open the app URL. You'll land on the sign-in page.
2. Choose **Create one** to register with a display name, email, and password,
   then sign in. (A fresh deployment first needs an admin — see the
   [Admin Guide](admin-guide.md#first-run).)
3. Sessions use short-lived access tokens with silent refresh; **Log out** ends
   the session.

## Projects

From the dashboard you can:

- **New project** — give it a name; it appears in your list.
- **Rename / Delete** — via the per-project actions menu (delete asks for
  confirmation).
- **Open** a project to enter the editor workspace.

Inside a project, the **file tree** lets you create `.tex` files and folders,
rename, move, and **upload** binary assets (images, PDFs, `.bib`). Uploads are
size- and type-checked.

## The editor

The editor is CodeMirror 6 with LaTeX syntax highlighting, line numbers, and
configurable font size. Edits are saved automatically — when collaborating, your
keystrokes sync live (see [Collaboration](#collaboration)); otherwise a save-status
badge shows **Saved** / **Unsaved changes**. Your content survives a reload.

## Compiling

1. Click **Compile**. The job runs server-side with the Tectonic engine.
2. The **PDF preview** (PDF.js) renders the result; use the toolbar to zoom, page,
   fit, and download.
3. The **Log** panel shows the compiler output; a **Problems** panel lists parsed
   errors/warnings as clickable annotations that jump to the offending line.

## SyncTeX

When a compile succeeds, Inkstave builds a SyncTeX map between source and PDF:

- **Forward** (source → PDF): jump from your cursor to the matching place in the
  preview.
- **Inverse** (PDF → source): click a spot in the preview to jump back to the
  source line.

## Version history

Every edit is captured into a compact history. Open **History** to:

- Browse the **timeline** of versions (load more as you scroll).
- Select a version to view its **diff** against the current text.
- **Restore** an earlier version (with confirmation) — it becomes a new version,
  so nothing is lost. You can also attach **labels** to versions.

## Collaboration

Share a project to work together in real time:

- **Share** → invite by email and pick a **role**: **owner**, **editor** (read +
  write), or **viewer** (read-only). The invitee accepts via an invite link.
- Collaborators editing the same document see each other's **keystrokes live**,
  plus **presence**: an "online now" list and labelled remote cursors.
- A **viewer** can open and read (and follow compiles/history) but the editor is
  read-only — they cannot change the document.

## The AI agent

Open the **Agent** panel to chat with Inkstave's built-in writing assistant. It
runs server-side as a LangGraph graph and can:

- **search the project**, **read files**, and **locate LaTeX sections**;
- **propose edits** as per-file unified diffs.

The agent **streams** its reply and tool activity as it works. Crucially, **it
never changes your documents on its own** — proposed changes appear as a
**Review changes** card. Open it to review the diff **hunk by hunk**, accept or
reject individual hunks, and only when you click **Apply** are the accepted
changes written to your document (live, through the same collaboration channel).

Agent usage is bounded by per-user/project **rate and cost limits** and a daily
budget; if you hit a limit the run is refused with a clear message. Untrusted
document/tool content is framed so it can't hijack the assistant.
