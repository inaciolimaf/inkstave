# Frontend

The browser application: a Vite and React single-page app that holds every screen of Inkstave, from the
public landing page to the editor workspace. It talks to the backend over REST, SSE and one WebSocket per
open document. It came from spec 09 and grew through specs 16-18, 24, 31, 32, 38, 46, 47, 61 and 64.

## Where it is

| Path | Role |
|---|---|
| `frontend/package.json` | Scripts and dependency ranges; pnpm 9.15.4 |
| `pnpm-lock.yaml` | Resolved versions; `pnpm-workspace.yaml` makes `frontend` the only workspace package |
| `frontend/src/main.tsx` | Mount: `ErrorBoundary`, `QueryClientProvider`, `AuthProvider`, `App`, `Toaster` |
| `frontend/src/router.tsx` | Route table, `createAppRouter`, `ROUTE_PATHS` |
| `frontend/src/config.ts` | Runtime configuration from `VITE_*` variables |
| `frontend/src/types.ts` | App-wide names over the generated schemas (`UserPublic`, `TokenPair`, `EditorPreferences`) |
| `frontend/src/lib/api-client.ts` | `apiClient`, `ApiError`, `refreshTokens` |
| `frontend/src/lib/token-store.ts` | `tokenStore` |
| `frontend/src/api/types.ts` | Generated from `docs/api/openapi.json` by `openapi-typescript`; never edited |
| `frontend/src/api/models.ts` | `Schemas`, the short name for `components["schemas"]` |
| `frontend/src/lib` | Shared helpers: formatting, shortcuts, downloads, palettes, validation, media query, `route-chunks.ts` (chunks loaded ahead of their route) |
| `frontend/src/components` | Shared UI: `app-shell.tsx`, `states.tsx`, `route-error.tsx`, `error-boundary.tsx`, `inkstave-logo.tsx` |
| `frontend/src/i18n/config.ts` | The global i18next instance and `NAMESPACES` |
| `frontend/src/i18n/locales` | `en/`, `pt/` and `landing.ts` |
| `frontend/src/routes` | 14 thin route components, one per screen, each loaded on demand by `lazy` in `router.tsx` |
| `frontend/src/modules` | 14 feature modules |
| `frontend/eslint.config.js` | Lint rules, size caps, boundaries, exceptions |
| `frontend/playwright.config.ts` | E2e projects and stack bring-up |

### Stack

| Role | Package | Range | Resolved |
|---|---|---|---|
| UI | `react`, `react-dom` | ^19.0.0 | 19.2.7 |
| Routing | `react-router-dom` | ^7.1.1 | 7.17.0 |
| Server state | `@tanstack/react-query` | ^5.62.11 | 5.101.0 |
| Forms | `react-hook-form`, `zod`, `@hookform/resolvers` | ^7.54.2, ^3.24.1, ^3.10.0 | 7.78.0, 3.25.76 |
| Editor | `@codemirror/view` and siblings; Vim and Emacs keymaps from `@replit` | ^6.36.0 | 6.43.1 |
| CRDT | `yjs`, `y-codemirror.next`, `y-protocols`, `lib0` | ^13.6.31 | 13.6.31 |
| PDF | `pdfjs-dist` | ^4.9.0 | 4.10.38 |
| Equation editor | `mathlive` (MIT), loaded on first use | 0.111.1 | 0.111.1 |
| i18n | `i18next`, `react-i18next`, `i18next-browser-languagedetector` | ^26.3.1, ^17.0.8, ^8.2.1 | 26.3.1, 17.0.8 |
| Spelling | `nspell`, `@types/nspell` | ^2.1.5, ^2.1.6 (dev) | 2.1.5, 2.1.6 |
| Styling | `tailwindcss`, `tailwindcss-animate`, Radix primitives | ^3.4.17 | 3.4.19 |
| Language and build | `typescript`, `vite` | ^5.7.2, ^5.4.11 | 5.9.3, 5.4.21 |
| API types | `openapi-typescript` | ^7.13.0 | 7.13.0 |
| Lint | `eslint`, `typescript-eslint`, `prettier` | ^9.17.0, ^8.19.1, ^3.4.2 | 9.39.4 for eslint |
| Unit tests | `vitest`, Testing Library, `jest-axe`, `jsdom` | ^2.1.8 for vitest | 2.1.9 |
| E2e tests | `@playwright/test` | ^1.49.1 | 1.60.0 |

### Modules

Each module has an `index.ts`. Other modules, routes and the app import only from it.

| Module | Holds | Public exports | Depends on |
|---|---|---|---|
| `frontend/src/modules/agent` | Agent panel, run reducer, SSE stream; its window also holds the project chat (`SideSwitch`) | `AgentPanel`, type `SideView` | diff-review |
| `frontend/src/modules/auth` | Session context, guards, theme application, login, register, setup, e-mail link pages | `AuthProvider`, `useAuth`, `RequireAuth`, `PublicOnly`, `useApplyTheme`, the 8 page components | none |
| `frontend/src/modules/collab` | Yjs provider, session hook, presence, cursors | `InkstaveWsProvider`, `useCollabDoc`, `collabDocUrl`, `usePresence`, `ConnectionStatusBadge`, `OnlineUsers`, type `CollabDocSession` | none |
| `frontend/src/modules/diff-review` | Inline review of agent proposals in the text, rebase, CRDT apply | `ReviewBar`, `useInlineReview`, `inlineReviewExtension`, `createEditorBridge`, type `DocumentBridge` | collab |
| `frontend/src/modules/discussion` | Project chat panel, its unread button, the shared project event stream, comment threads on the text (spec 118) | `ChatPanel`, `ChatButton`, `useChatUnread`, `useProjectEvents`, `subscribeProjectEvents`, `PROJECT_EVENT_TYPES`, `CommentsPanel`, `CommentsButton`, `useCommentThreads`, `useCommentMutations`, `commentMarks`, `encodeAnchor`, `resolveAnchor`, types `ProjectEvent`, `ProjectEventHandlers`, `CommentThread` | auth, sharing (the member list, through its index) |
| `frontend/src/modules/editor` | Workspace layout, CodeMirror, autosave, preferences, outline, LaTeX autocomplete (`completion/`), the Git clone dialog (spec 121), and the comments wiring (`useWorkspaceComments`) | `EditorWorkspace` | every other module except landing |
| `frontend/src/modules/file-tree` | Tree panel, dialogs, uploads, keyboard | `FileTreePanel`, `useProjectTree`, types `TreeEntity`, `TreeNode` | none |
| `frontend/src/modules/history` | Timeline, diff view, labels, restore | `HistoryPanel` | sharing |
| `frontend/src/modules/insert-tools` | Insert menu, symbol palette, table builder, equation editor (spec 114) | `InsertMenu` | none |
| `frontend/src/modules/landing` | Public marketing page | `LandingPage` | auth |
| `frontend/src/modules/notifications` | Bell, inbox list | `NotificationsBell` | none |
| `frontend/src/modules/pdf-preview` | Compile button, PDF viewer, log, problems, SyncTeX | `PreviewPane`, `useProblems`, `useSyncTex`, types `Problem`, `ProblemSeverity` | none |
| `frontend/src/modules/project-index` | Structure parser, include resolver, the index of sections, labels, `.bib` entries and files | `useProjectIndex`, `parseStructure`, `resolveIncludes`, `findCurrentEntry`, `parseBib`, types `StructureItem`, `ResolvedItem`, `IndexStatus`, `BibEntry`, `BibRef`, `LabelRef`, `ProjectFile` | none |
| `frontend/src/modules/projects` | Project list, dialogs, zip import, download | `ProjectsPage`, `getProject`, `useDownloadProject` | auth, notifications |
| `frontend/src/modules/spellcheck` | Project language, personal dictionary hooks, the spell worker and its engine, the CodeMirror extension, the suggestion menu | `SpellingMenuItems`, `SpellMenu`, `spellcheckFor`, `misspelledAt`, `useSpellcheck`, `usePersonalDictionary`, types `SpellLanguage`, `SpellcheckBinding` | projects |
| `frontend/src/modules/settings` | Settings sections, Git access tokens (spec 121), e-mail change confirmation | `SettingsPage`, `ConfirmEmailPage`, `putEditorPreferences` | auth, spellcheck |
| `frontend/src/modules/sharing` | Share dialog, invites, permissions | `ShareDialog`, `AcceptInvitePage`, `usePermissions`, `hasCapability`, `isReadOnly` | auth |

`editor` is the hub: it depends on 12 modules and nothing depends on it except `frontend/src/App.tsx` and
`frontend/src/routes/editor.tsx`. The graph has no cycle.

## Data

The frontend has no database. Server state lives in the React Query cache. Local state uses these keys:

| Key | Store | Holds |
|---|---|---|
| `inkstave.refresh_token` | `localStorage` | The refresh token |
| `inkstave.agent.open.<projectId>` | `localStorage` | Agent panel open flag |
| `inkstave.agent.dictation.cloudConsent` | `localStorage` | `1` once the user accepted cloud speech recognition |
| `inkstave.agent.dictation.sendAfter` | `localStorage` | `1` to send a message when dictation ends |
| `inkstave.agent.dictation.lang` | `localStorage` | `en-US` or `pt-BR`, the dictation language |
| `inkstave:split:<projectId>` | `localStorage`, via `autoSaveId` of `react-resizable-panels` | Size of the text and PDF panes |
| `inkstave:editor-settings` | `localStorage` | Line wrapping; the other fields are ignored |
| `inkstave:spellcheck-ignore:<documentId>` | `localStorage` | Words ignored in one document, lowercase |
| `inkstave:tree-expanded:<projectId>` | `sessionStorage` | Expanded folders |
| `inkstave.insert.recent-symbols` | `localStorage` | Up to 16 recently used symbol commands |

Access to these stores is wrapped in `try`/`catch`, so a blocked store degrades to defaults. The access token
lives only in a module variable of `frontend/src/lib/token-store.ts`. The `QueryClient` in
`frontend/src/main.tsx` sets `retry: false` and `refetchOnWindowFocus: false` for every query.

## Routes

These are browser routes. Every route sits under one root with `ErrorBoundary: RouteError` and
`HydrateFallback: Loading`.

| Path | File | Module | Access |
|---|---|---|---|
| `/` | `frontend/src/routes/landing.tsx` | landing | Public |
| `/setup` | `frontend/src/routes/setup.tsx` | auth | Public |
| `/login` | `frontend/src/routes/login.tsx` | auth | `PublicOnly` |
| `/register` | `frontend/src/routes/register.tsx` | auth | `PublicOnly` |
| `/settings/confirm-email` | `frontend/src/routes/confirm-email.tsx` | settings | Public, token in the link |
| `/verify-email` | `frontend/src/routes/verify-email.tsx` | auth | Public, token in the link |
| `/verify-email/resend` | `frontend/src/routes/resend-verification.tsx` | auth | Public |
| `/magic-link` | `frontend/src/routes/magic-link.tsx` | auth | Public, token in the link |
| `/reset-password` | `frontend/src/routes/reset-password.tsx` | auth | Public, token in the link |
| `/forgot-password` | `frontend/src/routes/forgot-password.tsx` | auth | `PublicOnly` |
| `/projects` | `frontend/src/routes/projects.tsx` | projects | `RequireAuth` |
| `/projects/:projectId` | `frontend/src/routes/editor.tsx` | editor, with `getProject` from projects | `RequireAuth` |
| `/settings` | `frontend/src/routes/settings.tsx` | settings | `RequireAuth` |
| `/invite/:token` | `frontend/src/routes/invite.tsx` | sharing | `RequireAuth` |
| `/join/:token` | `frontend/src/routes/join.tsx` | sharing (share links, spec 116) | `RequireAuth` |
| `*` | none | none | Redirects to `/projects` |

Token-link pages stay outside `PublicOnly` because a signed-in user may open a link in another tab.

## How it works

### Startup and session

1. `frontend/src/main.tsx` imports `@/i18n/config`, which initialises i18next before the first render.
2. `AuthProvider` runs `bootstrap` on mount. With a stored refresh token it calls `refreshTokens`, then
   `GET /api/v1/users/me`. `isBootstrapping` stays true until this ends.
3. `RequireAuth` shows a loading state during bootstrap. Without a user it reads `useSetupStatus` and redirects
   to `/setup` when no admin exists, otherwise to `/login`, keeping `from` in the location state.
4. `PublicOnly` sends a signed-in visitor to `/projects`, not to `/`, which is the marketing page.
5. `tokenStore.subscribe` drops the user whenever the access token disappears, for example after a failed
   refresh. `logout` always clears local state, even when the network call fails.

### API client

`apiClient` in `frontend/src/lib/api-client.ts` exposes `get`, `post`, `put`, `patch`, `delete`, `getText` and
`getBytes`, all on top of `requestRaw`.

1. `requestRaw` adds `Authorization: Bearer <access>` unless the call passes `auth: false`.
2. On a 401 of an authenticated, non-refresh request it awaits `refreshTokens`, then replays the request once.
3. `refreshTokens` shares one in-flight `performRefresh`, so concurrent 401s make one refresh call.
4. `performRefresh` posts to `/api/v1/auth/refresh`. A non-OK response clears the tokens. A network failure
   returns false and keeps them.
5. `toApiError` builds `ApiError` from the `{ error: { message, details } }` envelope, with a fallback to a
   string `detail` and then to the status text. Entries of `error.details` that carry `loc` and `msg` become
   `fieldErrors`, and the raw array stays in `details`.

Each module has an `api.ts` that maps wire shapes to camelCase domain types, using `Schemas["..."]` as the wire
type. Modules call `apiClient` at 72 sites. Three places do not use `apiClient`:

- `uploadFile` in `frontend/src/modules/file-tree/api.ts` and `importProjectZip` in
  `frontend/src/modules/projects/api.ts` use `XMLHttpRequest` for upload progress.
- `runEventsUrl` in `frontend/src/modules/agent/api.ts` and `compileEventsUrl` in
  `frontend/src/modules/pdf-preview/api.ts` build `EventSource` URLs with `?access_token=`.
- `InkstaveWsProvider` connects to the WebSocket with `?token=`.

To change the contract, run `make web-types`, which regenerates `docs/api/openapi.json` and
`frontend/src/api/types.ts`. CI runs `make web-types-check`, which fails when either file differs.

### Editor workspace

`frontend/src/routes/editor.tsx` reads the project id and renders `EditorWorkspace`, which renders the `Desk`
(spec 107). `EditorBar` in `frontend/src/modules/editor/editor-bar.tsx` is the one bar: the mark, the `h1`, the
open file, which opens the file list, share, notifications, a menu with history, download and the way back, and
Compile. Two resizable panels stay on screen, `EditorPane` and `PreviewPane`. `ContentPane` adds the status line
under the text and `FileDrawer`, the file list over the text, with the text `inert` while it is open.
`pickStartDocument` opens the root document, `main.tex` or the first `.tex` on arrival.

The Insert button (spec 114) sits in the bar before the notifications bell. `WorkspaceInsert` gives `InsertMenu`
the open view, the viewer's read-only state and the saved text of the main document.

Below 768 px, through `useMediaQuery`, `Panes` shows one pane at a time and `MobileTabs` switches between Content,
Preview and Agent. Both panes stay mounted. A successful compile shows the PDF; a problem or a PDF click shows
the text.

`PreviewPane` owns the compile, so it renders the Compile button and the output dock through portals, into
`compileSlot` and `outputSlot`. `EditorPane` and `CollabEditor` do the same with `statusSlot`. Without those props
each stays in its own row, which is what the pane tests render. In the status line the dock starts folded, opens
on Problems after a failure and folds warnings under errors (`foldQuiet`). After a failure the last good PDF stays
on screen with a notice.

- Opening a file: `FileTreePanel` calls `onSelectEntity`. A `doc` opens in the editor; a binary `file` shows
  `BinaryNotice`; a folder changes nothing.
- Outline: `OutlinePanel` in `frontend/src/modules/editor/outline-panel.tsx` lists the sections of the project, from
  `useWorkspaceOutline` (`frontend/src/modules/editor/workspace-outline.tsx`). `FileDrawer` has two tabs, Files and
  Outline (`drawer.tabs` in the `editor` namespace), and the last tab is remembered in `localStorage` through
  `frontend/src/modules/editor/outline-prefs.ts`, as is the pin. From 1280 px the outline can be pinned as a 14rem
  column left of the text. Entries open through `jumpToSource`, the same path as a problem.
- Project index: `useProjectIndex` in `frontend/src/modules/project-index/use-project-index.ts` fetches each
  document once through `GET /api/v1/projects/{id}/documents/{doc}` (query key `["project-index", projectId, docId]`,
  stale after 30 s). `parseStructure` (`parse-structure.ts`) blanks comments and verbatim-like environments, keeping
  the newlines, then reads `\part` to `\subparagraph`, `\input`, `\include`, `\subfile`, `\import` and `\label`.
  `resolveIncludes` (`resolve-includes.ts`) walks from the main document, which is `pickStartDocument`'s pick, and
  takes each file once. Past 200 documents or 2 M characters only the open file is indexed, and the outline says so.
  The open file is read from its CodeMirror view and debounced 300 ms by `useLiveSource`
  (`frontend/src/modules/project-index/use-live-source.ts`), so the index never lags what was typed.
  The same index feeds the completion: `labels` (every `\label`), `bib` (every `.bib` entry, parsed by
  `parse-bib.ts`, a key once with `alsoIn` for the other files that define it) and `files` (every document and
  file of the tree). `EditorWorkspace` hands it to `CompletionDataProvider`, which keeps it in a ref.
- LaTeX autocomplete (spec 112): `frontend/src/modules/editor/completion/`. `extension.ts` builds the
  `autocompletion` extension from nine sources, one file each in `sources/`: commands and environments (static
  data), bib keys, labels, `\input`/`\include`/`\subfile` paths, `\includegraphics`, `\bibliography`,
  `\addbibresource` and packages. Each source reads the text before the cursor on its line with a regex (the LaTeX
  language is a `StreamLanguage`, so there is no tree), and `guarded` silences every source in a comment or a
  verbatim environment (`context.ts`). The static data is `completion/data/*.json`, loaded by a dynamic `import()`
  in `load-data.ts` on the first completion, so it is outside the initial bundle. `packages.json` is generated by
  `scripts/build_completion_packages.py` from `infra/tectonic/packages.toml` and a curated list. A source ranks a
  completion accepted in this editor first among equal matches (`RecentUses`, `option.ts`).
  The switch is `EditorPreferences.autocomplete` (account, default on). `codemirror-extensions.ts` holds it in the
  `completion` compartment, so toggling it reconfigures the live view and removes the popup. Enter and Tab accept
  only in insert mode with the Vim keymap; Ctrl+Space opens the list. The popup takes the sheet tokens in both themes.
- Live editing: `useCollabDoc` creates one `Y.Doc`, `Y.Text("content")`, `Awareness`, `Y.UndoManager` (scoped to the
  text and the suggestions map) and `InkstaveWsProvider` per document, and tears them down on unmount. `CollabEditor`
  binds them to CodeMirror with `yCollab`, minus its `ySync` plugin, which Suggesting mode replaces (spec 119,
  `frontend/src/modules/collab/suggestions/`; see `docs/system/collab.md`). Editing stays off until the first sync, and stays off for a
  viewer (`isReadOnly`).
- Provider: it reconnects with backoff from 500 ms to 15 s. Close codes 4401, 4403 and 4404 are terminal.
- Before a compile or an agent message, `flushBeforeCompile` should await the session's `flush`, but nothing
  assigns its `flushRef`, so it does nothing today (`docs/known-gaps.md`).
- SyncTeX and diagnostics: `useSyncTex` resolves both directions, and `jumpToSource` opens another document when
  needed. `useProblems` feeds the problems panel, and `applyDiagnostics` draws those of the open file.

### Insert tools

`frontend/src/modules/insert-tools` holds the Insert menu (spec 114). Each tool writes to the open CodeMirror
view through `insertSnippet` or `insertBlock`, in one transaction marked `isolateHistory`, so one Undo takes back
that tool's change and nothing typed before it. In a live session the change reaches the CRDT through `yCollab`
like any keystroke. A viewer gets the menu disabled.

- Shortcuts: `Ctrl/Cmd+Shift+Y` opens the palette and `Ctrl/Cmd+Shift+E` the equation editor. `useShortcuts`
  looks up `mod+shift+<key>` before `mod+<key>`. CodeMirror, the Vim keymap and the Emacs keymap bind neither key.
- Symbol palette: `symbols/symbols.json` holds 275 symbols, each with a glyph, keywords and, when it needs one, the
  package. A centred dialog on a wide screen and a bottom sheet on a phone show the same panel. Choosing a symbol
  inserts it and keeps the palette open, so the package hint stays in reach. `insert-symbol.ts` adds `{}` for a
  command with arguments and a space after a letter command that a letter would follow.
- Table builder: `table-model.ts` is the draft, with immutable updates and limits of 30 rows and 15 columns.
  `to-latex.ts` writes the code and escapes cell text, unless "Cells contain LaTeX" is ticked, which also applies
  to the caption. `paste.ts` reads the tab and line separated text of a spreadsheet and fills the grid from the
  focused cell. The builder only creates tables; it never reads an existing `tabular`.
- Equation editor: `find-math.ts` returns the math under the cursor, with its delimiters. Save replaces only the
  body. `mathlive-loader.ts` imports MathLive and its font stylesheet when the dialog opens. If that fails, the
  dialog shows a textarea. The decision is in `docs/adr/0111-mathlive-equation-editor.md`.
- Packages: `PackageHint` checks the saved text of the main document. "Add it" writes `\usepackage{…}` before
  `\begin{document}` of the open text, when that text has one; otherwise it says where the line goes.

### Compile preview

`useCompile` in `frontend/src/modules/pdf-preview/hooks/useCompile.ts` flushes and requests the compile.
`useCompileStream` in `frontend/src/modules/pdf-preview/hooks/useCompileStream.ts` follows the `status` events of an `EventSource`. When SSE is missing or fails before a terminal status, it polls every
`compilePollIntervalMs`. A failed flush does not block the compile.

### Agent and diff review

1. `AgentPanel` is a non-modal window in the lower right corner, a sheet on a phone. It stays mounted while folded,
   so a run goes on. It uses `useAgentChat`, which lists sessions and calls `onBeforeSend` before a run starts.
   The editor reaches it through `request`: a selection from `AskAgentButton` becomes a chip whose text `withQuote`
   adds to the next message, and "Fix with the agent" on an error sends a message at once.
2. `startRun` posts the message. `openStream` opens an `EventSource` for `token`, `tool_call`, `tool_result`,
   `diff_proposed`, `done` and `error`, and passes each event to `applyEvent`.
3. `applyEvent` in `frontend/src/modules/agent/reducer.ts` drops repeated `seq` values and unknown event types.
4. A proposal card calls `useInlineReview.open`, which switches the editor to the proposal's document and starts
   the review on that document's CodeMirror view. There is no dialog (spec 110). `inlineReviewExtension` is part of
   every editor's extensions and draws nothing until a review starts: removed lines struck through on the error
   tint, added text in a block under them, and a toolbar per open hunk with Accept and Reject. A blocked hunk
   (its old lines changed) gets only Reject. A viewer sees the drawing and no buttons.
5. Accept writes that hunk: `bridge.readContent` gives the live text, `rebaseHunks` applies the one hunk, and
   `bridge.applyContent` writes it. Reject changes no text. `ReviewBar` above the text shows "Change n of m", moves
   between changes, and offers Accept all and Reject all. Keys: `Alt+]` and `Alt+[` move, `Alt+Enter` accepts,
   `Alt+Backspace` rejects.
6. When the last hunk is decided, `recordDecision` posts the lists to the outcome route and the review closes. The
   card shows the returned status. The state field re-places hunks on every change, so a collaborator's edit
   inside a hunk blocks it while the rest stay acceptable. `createEditorBridge` opens a short-lived provider per
   document, and `applyTargetToYText` writes one minimal edit in a transaction tagged `agent-apply`.

### Dictation (spec 115)

The microphone beside Send in the agent's message box uses the browser's `SpeechRecognition` and nothing else.
`voice/speech.ts` is the only file that touches it, and it hands over text only: Inkstave never receives, stores
or sends audio, and it never calls `getUserMedia`. The button is absent where the API is missing.

1. `useDictation` (`voice/use-dictation.ts`) runs `idle → asking-consent → listening → idle`. `startSession`
   (`voice/session.ts`) owns the recognizer and its timers: two seconds of silence, or a second press, stop it;
   a browser that never reports the end is cut off after 1.5 s.
2. `processLocally` is set when `SpeechRecognition.available` answers `available` for the language. Otherwise the
   first use shows the notice that the browser may send audio to its speech service; the answer is kept in
   `localStorage`. Cancel starts nothing.
3. Interim words show in a muted line above the box; each final phrase is appended to the draft (`useComposer`,
   `frontend/src/modules/agent/use-composer.ts`). Nothing is sent unless "Send after dictation" is on.
4. Folding the panel, a send, an unmount or Escape while listening abort the session; Escape also drops the words
   that session added. Ctrl/Cmd+Shift+M toggles it while the panel has focus.
5. Errors (`not-allowed`, `no-speech`, `network`, `audio-capture`) are shown in plain words under the box, never as
   a dialog. The strings live in the `agent` namespace under `dictation`.

### Notifications, history, sharing

- `NotificationsBell` polls the unread count and loads the list only while open. Dismiss is optimistic and rolls
  back on failure.
- `HistoryPanel` is shown for an open `doc`. Its write controls need the `doc_write` capability, read through
  `usePermissions` and `hasCapability`.

### Spell check

Spec 113. The spelling language belongs to the project: `projects.spellcheck_language` is `off`, `en-US` or
`pt-BR`, and any member who may write documents changes it with `PATCH /api/v1/projects/{id}/settings`.
`useSpellLanguage` reads it from the project query, which the editor bar and the editor share. The "Create
project" dialog asks for it (English or Portuguese, `spellcheck-language-field.tsx`), preselects the creator's interface
language (`defaultSpellcheckLanguage` in `frontend/src/modules/projects/use-projects.ts`) and says the editor menu
changes it later.

1. `useSpellcheck(projectId, documentId)` builds a `SpellcheckBinding` for the open document. It is null while the
   language is `off` or the personal dictionary has not loaded, and the dictionary is fetched only while a language is
   on. `accepts` answers for the personal dictionary and for the document's ignore list, compared in lowercase.
2. `EditorPane` passes the binding to `CodeMirrorEditor` and `CollabEditor`. They add `spellcheckFor(binding, ...)` through
   the `spell` compartment, so a change of language or words reconfigures the view and keeps it.
3. `spellcheckExtension` is a view plugin. 400 ms after an edit, a scroll or a reconfiguration it takes the words of
   `checkableWords` (`tokenize.ts`) for the visible lines plus 50 lines either side, asks the checker about the words
   it has not asked about in this language, and marks the misspelled ones that `accepts` does not keep with the
   `cm-misspelled` class (a wavy underline in `--error-text`).
4. `spell-client.ts` owns one worker per tab, created by the first request, so a project with the check off never
   starts it. Each request has a 15 s deadline. `spell.worker.ts` answers with `spell-engine.ts`: nspell over the
   Hunspell pair at `dictionaries/<language>.aff.gz` and `.dic.gz`, unzipped in the worker and loaded once per language.
   A failed load is forgotten, so the next request retries.
5. A right click on a mark (a long press where the browser sends `contextmenu`) opens `SpellMenu`: up to five
   suggestions, then "Add to dictionary" (`POST /api/v1/me/dictionary`, applied at once) and "Ignore in this document"
   (`localStorage`). A right click elsewhere returns false from the handler, so the native menu stays.
6. A failed dictionary load calls `reportFailure`: the status line shows a notice and the plugin stops marking. Editing
   goes on.

The language menu is `SpellingMenuItems`, in the editor bar's "More actions" menu. The settings page lists the personal
dictionary with `DictionarySection`.

Dictionaries are static files in `frontend/public/dictionaries/`, served as they are and never bundled. They are not
committed: `frontend/scripts/copy-dictionaries.mjs` writes them from the pinned npm packages `dictionary-en` and
`dictionary-pt` (devDependencies) before `dev` and `build` (the `predev` and `prebuild` scripts). Each `.aff` and `.dic`
is gzipped, because the Portuguese list is 4.5 MB raw, and the package's licence notice is copied beside it. The
output folder is git-ignored. Their licences are in the ADR `docs/adr/0113-spell-check-dictionaries.md`:

| Language | Files | Source | Licence |
|---|---|---|---|
| `en-US` | `en-US.aff.gz`, `en-US.dic.gz`, `en-US.LICENSE.txt` | npm `dictionary-en` 4.0.0 (wooorm/dictionaries, from SCOWL) | `(MIT AND BSD)`; the notices are in the `.LICENSE.txt` |
| `pt-BR` | `pt-BR.aff.gz`, `pt-BR.dic.gz`, `pt-BR.LICENSE.txt` | npm `dictionary-pt` 4.0.0 (wooorm/dictionaries, from LibreOffice VERO pt_BR) | `(LGPL-3.0 OR MPL-2.0)`; used under MPL-2.0, unmodified |

The engine is `nspell` 2.1.5 (MIT), with `@types/nspell` 2.1.6 for development. To add a language: add its npm
dictionary package to devDependencies and to `sources` in `frontend/scripts/copy-dictionaries.mjs`, check its licence
in the ADR, add it to `SPELL_LANGUAGES` and `DICTIONARY_LANGUAGES` in `frontend/src/modules/spellcheck/types.ts`, and
add its label to `spelling-menu-items.tsx` and both locales.

### Internationalisation

Every screen is bilingual. `frontend/src/i18n/config.ts` builds one global i18next instance:

- Languages: `en` and `pt`, with `en` as fallback. `load: "languageOnly"` collapses `pt-BR` and `pt-PT` to `pt`.
- Detection: `navigator`, then `htmlTag`. `caches: []` means nothing persists. The UI has no language switcher;
  `changeLanguage` is not called anywhere.
- `<html lang>` follows the active language.
- Namespaces, 14 in total: `common` (default), `landing`, `auth`, `projects`, `editor`, `files`, `preview`,
  `agent`, `review`, `history`, `insert`, `settings`, `sharing`, `notifications`.

Thirteen namespaces have one file each under `frontend/src/i18n/locales/en` and `frontend/src/i18n/locales/pt`.
Twelve of them export `Dict` from English and type Portuguese with it, so `tsc` catches a missing key. `common` does not.
`landing` keeps both languages in `frontend/src/i18n/locales/landing.ts`, with `landingPt` typed as
`typeof landingEn`. Components call `useTranslation`; hooks outside React call `i18n.t` from the same instance.

Tests read the English strings, so changing English text can break them. Role labels stay lowercase in the DOM
and use a `capitalize` CSS class.

### Shared components and states

`frontend/src/components/states.tsx` exports `Loading`, `ErrorState` and `QueryView`. `QueryView` renders loading,
error with retry, or `children(data)`, and treats a settled query without data as an error.

Crashes are caught at two levels. `RouteError` handles errors inside the router: its retry resets inactive
queries and navigates to the same URL. `frontend/src/components/error-boundary.tsx` wraps the whole tree.

Reuse is enforced by lint. Each rule has one allowed file:

| Rule | Use | Allowed in |
|---|---|---|
| No hex colours | Design tokens | `frontend/src/lib/palettes.ts` |
| No `toLocale*String` | `formatNumber`, `formatDate`, `formatDateTime` | `frontend/src/lib/formatting.ts` |
| No `keydown` listener | `useShortcuts` | `frontend/src/lib/shortcuts.ts` |

### Landing styling

`frontend/src/modules/landing/landing-page.tsx` imports `frontend/src/modules/landing/landing.css` and wraps the
page in `.landing-root`. All landing tokens (`--paper`, `--ink`, `--rule`) and motion rules are defined under
that class. The Tailwind utilities that use those tokens, declared in `frontend/tailwind.config.ts`, resolve only
inside it, so the app shell stays on its own tokens. `frontend/index.html` loads Inter, JetBrains Mono and
Newsreader from Google Fonts on every page. The landing respects `prefers-reduced-motion`.

### Tests

`frontend/vitest.config.ts` runs Vitest in the custom environment `frontend/src/test/jsdom-environment.ts`, which keeps Node's
`AbortController` for React Router under jsdom. `frontend/src/test/setup.ts` adds jest-dom, loads i18n and stubs
the browser APIs that Radix, CodeMirror and PDF.js expect.

- 128 test files: 121 next to the code in `frontend/src` and 7 in `frontend/tests`.
- `frontend/tests/router.test.tsx` runs the real router and providers over `fakeApi` from
  `frontend/tests/helpers/screen.tsx`.
- `frontend/tests/module-boundaries.test.ts` fails on an import cycle between modules.
- `frontend/tests/e2e-routes.test.ts` fails when `frontend/e2e/support/routes.ts` falls behind the router.
- Coverage floor: 75% for statements, branches, functions and lines, set in `frontend/vitest.config.ts`.

`frontend/playwright.config.ts` runs against a real backend, ARQ worker, Postgres and Redis, with `COMPILE_MODE=mock` and
`LLM_STUB=true`. Its `webServer` entries start `frontend/e2e/bringup-backend.sh` and a Vite preview of a fresh
build. `frontend/e2e/global-setup.ts` creates the first admin and two users. The default `page` fixture in
`frontend/e2e/support/fixtures.ts` signs in as user A. Default workers: 2, because the suite shares one backend.

| Project | Runs | Browser | Make target |
|---|---|---|---|
| `smoke` | Everything except `@full` | Desktop Chrome | `make e2e-smoke` (CI) |
| `routes` | `frontend/e2e/routes.spec.ts`: 15 routes open without a crash | Desktop Chrome | `make e2e` |
| `mobile` | `frontend/e2e/mobile.spec.ts`: 15 routes fit 390x844 | Desktop Chrome, with touch and that viewport | `make mobile` |
| `flows` | `frontend/e2e/flows`: 14 files of real journeys, without `@full` | Desktop Chrome | `make e2e-flows` |
| `full` | `@full` only, in `frontend/e2e/flows/full.spec.ts` | Desktop Firefox | `make e2e-all`, with `smoke` |

Name the projects when running Playwright. A bare `playwright test` runs the slices on top of `smoke`.
`frontend/e2e/harness.spec.ts` checks the compile and LLM stubs through the API, without a page.

## Rules and guarantees

| Invariant | Test |
|---|---|
| The access token never reaches `localStorage` | `frontend/src/lib/token-store.test.ts`, "never writes the access token to localStorage" |
| Concurrent 401s make one refresh | `frontend/src/lib/api-client.test.ts`, "dedupes concurrent 401s into a single refresh" |
| A failed refresh clears tokens and throws | `frontend/src/lib/api-client.test.ts`, "clears tokens and throws when refresh fails" |
| Logout clears local state on network failure | `frontend/src/modules/auth/auth-context.test.tsx`, "clears local state even when the logout network call fails" |
| Signed-out visitors go to `/setup` or `/login` | `frontend/src/modules/auth/require-auth.test.tsx`, "redirects to /setup when unauthenticated and no admin exists yet (AC4)" |
| A rendering crash shows the app's error screen and can recover | `frontend/tests/router.test.tsx`, "shows the app's translated error screen and recovers with try again" |
| Modules have no import cycle | `frontend/tests/module-boundaries.test.ts`, "has no import cycle between modules" |
| The e2e route list equals the router | `frontend/tests/e2e-routes.test.ts`, "covers every route of the router, and nothing else" |
| No route crashes | `frontend/e2e/routes.spec.ts` |
| No route but the editor scrolls sideways at 390 px | `frontend/e2e/mobile.spec.ts` |
| Agent edits apply only when accepted, and only accepted hunks | `frontend/src/modules/diff-review/inline-review-actions.test.ts`, "accepting a hunk" and "recording the outcome" |
| A hunk that no longer matches is never applied | `frontend/src/modules/diff-review/hunks.test.ts`, "never includes a blocked hunk in the rebased target" |
| An agent apply keeps a concurrent edit elsewhere | `frontend/src/modules/diff-review/crdt-apply.test.ts`, "converges collaborators and preserves an unrelated concurrent edit (AC6)" |
| Assistant Markdown cannot run scripts | `frontend/src/modules/agent/transcript.test.tsx`, "sanitizes assistant content (no script execution) (AC10)" |
| Inkstave never receives or stores audio | `frontend/src/modules/agent/voice/speech.test.ts`, "passes final phrases once and the pending words as interim text" |
| Dictation never sends a message unless the user chose it | `frontend/src/modules/agent/voice/use-dictation.test.tsx`, "reports sendAfter false by default, so dictation alone never sends" |
| Cloud recognition needs the user's consent first | `frontend/src/modules/agent/voice/use-dictation.test.tsx`, "asks before cloud recognition and starts nothing when cancelled" |
| Document text never leaves the browser for spell checking | `frontend/src/modules/spellcheck/spell-engine.test.ts`, "has no network API besides fetching the dictionary files" |
| Commands, keys and math are never checked | `frontend/src/modules/spellcheck/tokenize.test.ts`, the "skips" table |
| A dictionary load failure never blocks editing | `frontend/src/modules/spellcheck/spellcheck-extension.test.ts`, "keeps the editor working when the dictionary fails to load" |
| Dictionaries are not in the initial bundle | `make web-budget` (the dictionaries are in `public/`, outside the bundle) |
| The provider stops on a terminal close | `frontend/src/modules/collab/InkstaveWsProvider.lifecycle.test.ts`, "stops reconnecting after a terminal auth close (4401) — no spin (spec 35)" |
| A viewer cannot type in the editor | `frontend/src/modules/editor/CollabEditor.test.tsx`, "is non-editable with a 'View only' banner when readOnly (spec 34 AC10)" |
| Modules import each other only through `index.ts` | No dedicated test; `no-restricted-imports` in `frontend/eslint.config.js` |
| Shared code does not import a module | No dedicated test; `no-restricted-imports` in `frontend/eslint.config.js` |
| Portuguese has every key English has | No dedicated test; the `Dict` type, checked by `tsc`, except `common` |
| Comments and verbatim never produce outline entries | `frontend/src/modules/project-index/parse-structure.test.ts`, "skips a commented-out section" and "skips verbatim-like environments" |
| Includes are followed once, cycles cut | `frontend/src/modules/project-index/resolve-includes.test.ts`, "renders each file once and stops at a cycle" |
| The current section is marked for assistive tech | `frontend/src/modules/editor/outline-panel.test.tsx`, "marks the section that holds the cursor for assistive tech" |
| Past the caps only the open file is indexed | `frontend/src/modules/project-index/build-index.test.ts`, "keeps only the open file past the document cap" |
| Completion never fires in comments or verbatim | `frontend/src/modules/editor/completion/context.test.ts`, "is silent at the cursor of a comment and speaks again after it" and "is silent inside a verbatim block" |
| A malformed `.bib` never breaks completion | `frontend/src/modules/project-index/parse-bib.test.ts`, "keeps the readable entries of a half-typed file" and "skips a malformed entry and keeps reading the next one" |
| Completion data is not in the initial bundle | `make web-budget` (the data is dynamic imports) |
| Data files are sorted and unique | `frontend/src/modules/editor/completion/data.test.ts` |

## Settings

Vite reads these at build time. The template is `frontend/.env.example`. `frontend/Dockerfile` builds with empty
`VITE_API_BASE_URL` and `VITE_COLLAB_WS_URL`, which means same origin.

| Variable | Default | Effect |
|---|---|---|
| `VITE_API_BASE_URL` | `http://localhost:8000` | Backend origin; empty means same origin |
| `VITE_COLLAB_WS_URL` | Derived from the API origin or the page origin, plus `/ws/collab` | Collab WebSocket base |
| `VITE_COMPILE_POLL_INTERVAL_MS` | `1000` | Compile polling fallback |
| `VITE_NOTIFICATIONS_POLL_INTERVAL_MS` | `60000` | Unread count polling |
| `VITE_AGENT_ENABLED` | on; only `false` hides it | Agent panel and toolbar button |

## Points of attention

- **The outline refreshes coarsely for files it does not have open.** Spec 111 asked for a collaboration signal
  when someone saves another file. The index has none: it refetches a document when the writer leaves it, when the
  window regains focus after 30 s, and when a new document appears in the tree. Edits by others show up then.
- **The outline's main document is not the compile's.** The server compiles `main.tex`, or else the shallowest
  `.tex` that declares `\documentclass` (`backend/src/inkstave/modules/compile/running/service.py`). The outline
  uses `pickStartDocument`, which prefers `root_doc_id`. The two differ on a project with no `main.tex` or with a
  root document elsewhere.
- **No "selected" colour token exists.** The current outline row uses `bg-accent` with a `border-foreground` stripe,
  the way the file tree marks its selection.
- **`hidden` loses to a Tailwind `flex` class.** Both selectors have the same specificity and Tailwind's utilities
  come later, so the drawer's `aside` takes no `flex`: the tabbed layout sits in a wrapper inside it.
- **The spell-check menu is a Radix popover, not a Radix context menu.** A context-menu trigger suppresses the native
  menu for every word of the editor. The popover is anchored at the pointer by a zero-size `PopoverAnchor` and
  is opened by the plugin's `contextmenu` handler only over a misspelled word. Its items are buttons: Tab reaches
  them, arrow keys do not (`docs/known-gaps.md`).
- **Spell check ignores what the dictionary cannot judge.** Words with digits, contractions and elisions (`don't`,
  `d'água`), all-caps words of up to five letters and one-letter words are not checked. A `[…]` option of a command
  is skipped too, so `\section[short]{Long}` does not check `short`.
- **`QueryView` shows the error over stale data.** A failed refetch replaces cached data with the error, and a
  settled query with no data, such as a paused one, counts as an error. `file-tree-body.tsx` keeps the tree on a
  background failure by rendering its alert above it. The invite 410 and the setup skeleton stay early returns.
- **API types are narrowed by hand.** The code has no user-defined type predicate. Responses reach modules
  through `apiClient.get<T>`, an unchecked cast with no runtime validation.
  - Ten casts cover API data: 4 role casts in `frontend/src/modules/sharing/api.ts`, 2 in
    `frontend/src/modules/agent/api.ts`, 3 over `JSON.parse` (file-tree and projects uploads, compile SSE), and
    `TokenPair` in `frontend/src/lib/api-client.ts`. `AgentEvent` gets its type from an untyped `JSON.parse`.
  - The 4 role casts are redundant: the generated fields are already `MembershipRole` and `InviteRole`, the same
    unions as `Role` and `InviteRole` in `frontend/src/modules/sharing/types.ts`.
  - The comment on `CompileStatus` in `frontend/src/modules/pdf-preview/types.ts` is partly stale: generated
    `status` is already `CompileJobStatus`. Only `artifact_manifest` is still loose.
  - Hand-written unions repeat generated ones: `CompileJobStatus`, `ImportStatus`, `Role`, `InviteRole`. The
    `Permissions` interface repeats `PermissionsRead`.
  - Notification payloads are `Record<string, unknown>`, read through `String(...)` and one `typeof` check.
- **Size and lint exceptions.** `frontend/eslint.config.js` caps functions at 100 lines and files at 300, without
  counting blanks and comments.
  - Neither cap has an exception.
  - Tests are outside the caps and reuse rules. `frontend/src/api/types.ts` is not linted.
  - `react-refresh/only-export-components` is off for `frontend/src/components/ui`, test support and the router.
  - The boundary rule covers `frontend/src` only, so `frontend/tests/helpers/screen.tsx` imports
    `@/modules/auth/auth-context` directly.
  - `frontend/src` has 8 inline `eslint-disable` comments, and no `any`, `ts-ignore` or `ts-expect-error`.
- **The REST autosave path does not run in a real build.** `collabWsUrl` is never empty, because `||` falls
  through to a derived URL, so `COLLAB_ENABLED` in `frontend/src/modules/editor/editor-workspace.tsx` is always
  true. `frontend/.env.example` still says an empty value falls back to REST autosave, which is wrong. The
  `useDocumentAutosave` branch stays tested, but only tests that leave `collabEnabled` off reach it.
- **Non-`apiClient` calls have no refresh.** XHR uploads, `EventSource` URLs and the WebSocket use the access token
  as it stands, and the last two put it in the URL because those APIs cannot set headers. An expired token fails an upload with no retry. On the WebSocket, a reconnect with an expired token
  gets 4401, which is terminal, so the editor stays offline until the session is recreated.
- **No code splitting.** Routes load eagerly, with no `lazy` or `import()`, so the landing ships with CodeMirror.
- **Server text is English.** `ApiError.detail` comes from the backend, and `RouteError` and others show it as is,
  so a Portuguese user can see English. The invite notification also prints `payload.role` raw, without
  translating it.
- **Dead code.** `useDocument` in `frontend/src/modules/editor/use-document.ts` has no caller; only `documentKey` is
  used.

## Frontend standard

The `frontend-standard` skill applies, with the identity in `specs/106-visual-identity-manuscript/spec.md`.

- **Skeleton.** `Manuscript`, `TitlePage` and `Desk` (`frontend/src/components/manuscript.tsx`) are the root
  of a screen, each marked `data-manuscript`; `ManuscriptHeader` and `Rule` build it. The palette is in
  `frontend/src/index.css`. `AuthShell` (title pages) and `ErrataSlip` (error screens) sit on `TitlePage`;
  `SettingsSection` is a ruled section of settings. `Card` is gone. Below 1024 px the editor bar shows icons
  only, and `sheetTheme` paints CodeMirror with the page tokens in both themes.
- **Shell.** `AppShell` (`frontend/src/components/app-shell.tsx`) is the root route's element. It renders a
  skip link, moves focus to the screen's `h1` (or `main`) when the pathname changes, and sets
  `document.title` from the route's `handle.title`, a key of the `common` namespace. Screens render one
  `main` and one `h1` and never manage focus or the title. `RouteError` sits on a pathless child of the
  root, so errors render inside the shell.
- **Colour.** Components use roles only (`success`, `warning`, `error-soft`, `error-text`, `backdrop`,
  `page`); values live in `frontend/src/index.css`. An overlay on the PDF page or in the editor uses a
  translucent solid (`warning/30`), because the PDF page is white in both themes. Text uses `error-text`,
  never `destructive`. Landing colours are tokens scoped to `.landing-root`.
- **Focus.** One solid `:focus-visible` outline in `frontend/src/index.css`; components add no rings. Menu
  items show focus with `focus:bg-accent`, and tree rows draw the outline from their focused `treeitem`.
- **Motion.** Durations are `duration-fast|base|slow`, or `var(--motion-*)` in CodeMirror themes, mirrored in
  `frontend/src/lib/motion.ts`. Reduced motion is global in `frontend/src/index.css`.
- **Fonts.** Self-hosted from Fontsource, latin and latin-ext only. `frontend/src/fonts.ts` registers
  Source Sans 3, JetBrains Mono and upright Newsreader; Inter and Newsreader italics load with the landing chunk.

| Rule | Guarantee |
|---|---|
| Initial JS at most 250,000 bytes gzip | `make web-budget` (`scripts/check-bundle.mjs`), in CI |
| Only cheap properties animate | `frontend/tests/keyframes.test.ts` |
| Text 4.5:1, focus and control borders 3:1, both themes | `frontend/tests/contrast.test.ts` |
| Inputs, textareas, selects and switches draw their edge with `control-edge` | `frontend/tests/css-rules.test.ts` |
| Text over a presence colour reaches 4.5:1 through `inkOn` | `frontend/src/lib/palettes.test.ts` |
| Pointing at or focusing a project warms the editor chunk and the project query | `frontend/src/modules/projects/project-index.prefetch.test.tsx` |
| `renderScreen` returns only once the lazy route has settled | `frontend/tests/helpers/screen.tsx` |
| No `100vh`, `h-screen` or `min-h-screen` | `frontend/tests/css-rules.test.ts` |
| No raw Tailwind hue, no size outside the type tokens | `palette` and `type` groups in `frontend/eslint.config.js` |
| Axe over every route, both themes, and over the project list and editor with a real project; one `main`, one `h1` | `frontend/e2e/a11y.spec.ts` |
