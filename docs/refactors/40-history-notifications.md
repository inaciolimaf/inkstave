# Refactor 40 — History & Notifications (Phase 5 hardening)

A structured review of specs 36–39 (history capture/storage, history API/restore/diff,
history UI, notifications & email). Findings were surfaced by two read-only audit passes
over the backend, triaged by risk vs. value, and the worthwhile fixes applied with
regression tests. **No new features.** Suite: **619 passed / 1 skipped in 49s** (backend),
282 frontend — both under the 2-minute budget. ruff + mypy + eslint/tsc clean.

## Applied fixes

| # | Area / spec | File | Severity | Fix | Test |
|---|-------------|------|----------|-----|------|
| 1 | Capture — data loss on shutdown (36) | `app.py` lifespan | **HIGH** | `HistoryCaptureService.flush_all()` existed but was **never called**; buffered (un-debounced) edits were lost on graceful shutdown. Now invoked in the lifespan `finally` **before** engine dispose, guarded so a flush error can't block shutdown. | `test_refactor_40.py::test_flush_all_persists_buffered_updates` |
| 2 | Capture — storage integrity (36) | `db/models/history.py` + migration `f6a8c2d24e57` | MED | The "exactly one of inline payload / blob key is non-NULL" invariant was app-enforced only. Added DB `CHECK` constraints (`ck_history_updates_payload_xor`, `ck_history_chunks_base_xor`) so a future capture/compaction bug can't silently corrupt a version. | `test_refactor_40.py::test_payload_xor_check_rejects_bad_row` |
| 3 | Restore — atomicity (37) | `history/restore.py`, `history/labels.py` | MED | Two ordering bugs: (a) the broadcast fired **before** history capture, so clients could see a restore that failed to record; (b) a duplicate `label_name` raised only *after* mutating the live doc. Now: fail fast via `ensure_label_available` **before** any mutation, and `redis_bridge.publish` runs **last** (after capture + flush + label). | `test_refactor_40.py::test_restore_duplicate_label_fails_fast` (409, no new version, no broadcast) |
| 4 | Email — HTML injection (39) | `mailer/templates.py` | MED (security) | `project_name` / `inviter_name` / `user_name` (user-controlled) were interpolated into the HTML email body unescaped — a stored-content → HTML-email injection. Now `html.escape()`d (text body unchanged). | `test_email_sender.py::test_project_invite_html_is_escaped` |
| 5 | Notifications — de-dupe UX (39) | `notifications/service.py` | LOW | A re-issued invite (de-dupe path) reset `read_at`/`expires_at` but kept its old `created_at`, so it didn't resurface in the `created_at DESC` list. Now bumps `created_at` on refresh. | `test_notifications_service.py::test_dedupe_refresh_resurfaces_notification` |

## Added coverage (verifying already-correct behaviour — Acceptance criteria 3, 4)

- **Reconstruction exactness after compaction (AC4):** capture across a sealed chunk boundary,
  run `compact_history`, and assert `reconstruct_state(head)` is **byte-identical** before/after
  — `test_refactor_40.py::test_compact_preserves_reconstructed_state`.
- **Restore correctness (AC3):** already covered by `test_history_restore.py` (live text equals
  target, new version created, all prior `history_*` rows retained, mocked broadcast invoked);
  the new fail-fast test adds the atomic-on-failure case.
- **Diff edge cases:** extended `test_history_diff.py` round-trip cases — both-empty, all-removed
  + all-added, and changing an unterminated final line.

## Spec 38 — history UI §5.1 review

Each enumerated spec-38 review item from spec 40 §5.1, with a fix / skip /
verified decision and rationale.

| Item | Decision | Rationale / covering test |
|------|----------|---------------------------|
| Loading / empty / error states present | **verified correct** | `HistoryTimeline` renders skeletons while `isLoading`, a "No history yet." empty state, and a `role="alert"` error with a Retry button; `HistoryDiffView` mirrors this with its own loading/empty/error/binary/too-large branches. Covered by `HistoryTimeline.test.tsx` and `HistoryDiffView.test.tsx`. |
| Pagination correctness | **verified correct** | `useVersions` is a `useInfiniteQuery` with `getNextPageParam` driven by `hasMore`/`nextBefore`; the "Load more" button is gated on `hasNextPage` and disabled while `isFetchingNextPage`. Terminates on the API's gap-aware cursor (backend pagination already tested in `test_history_*`). No change. |
| Selection model (single vs range) bugs | **verified correct** | `HistoryPanel.onSelect` distinguishes single-select (click → `primary`, clears `compare`) from range-extend (shift-click → `compare`), derives `from = min`, `to = max` (or `"current"` for a lone selection), and resets both on `docId` change. Behaviour exercised via the timeline's `aria-pressed` rows. No bug found. |
| Diff fallback rendering | **verified correct** | `HistoryDiffView` has explicit fallbacks for binary (`This document has no text diff.`), too-large, and no-changes diffs in addition to the hunk view. Covered by `HistoryDiffView.test.tsx`. No change. |
| Restore confirmation copy + flow | **verified correct** | `RestoreVersionButton` gates the restore behind an explicit confirmation dialog (copy states a new version is created, optional label); the panel description repeats "restoring creates a new version". Covered by `RestoreVersionButton.test.tsx`. No change. |
| No direct editor mutation | **verified correct** | The UI never writes document text directly: restore goes through the spec-37 `restoreVersion` API (server creates the new version + broadcasts), and the panel only reads/diffs. No client-side CRDT/editor mutation path exists in the history feature. No change. |
| a11y: markers not colour-only | **verified correct** | Diff rows carry an explicit `+`/`-`/` ` text marker column alongside the green/red row tint, so added/removed are distinguishable without colour. No change. |
| a11y: focus trapping | **verified correct** | The panel is a shadcn/Radix `Sheet` (`SheetContent`), which provides modal focus-trapping and Escape-to-close out of the box; timeline rows are keyboard-operable (`role="button"`, `tabIndex=0`, Enter/Space, visible focus ring). No change. |
| Labels appear as badges in the **detail header** (§5.3.4) | **fixed** (issue 152, separate fix-pack files) | The detail header badges were the one genuine UI gap. Fixed in `HistoryDiffView.tsx` / `HistoryPanel.tsx`: the selected version's labels now render as `Badge`s above the diff, reusing the timeline row-badge styling. |

## Deliberately skipped (with rationale)

| Area / spec | Finding | Decision + rationale |
|-------------|---------|----------------------|
| Capture (36) | Timer-fired flush is fire-and-forget (`asyncio.ensure_future`), untracked at shutdown | **SKIP** — finding #1 (`flush_all` on shutdown) covers the buffered-data case; `flush_doc` is idempotent (lock + empty-buffer guard), so a racing in-flight flush is harmless. Tracking every task adds complexity for a narrow window. |
| Capture (36) | Version `next = max+1` + open-chunk insert can race across **multiple app instances** → `IntegrityError`, losing that flush | **SKIP** — the deployment model is single-worker (one collab process per the spec); the per-doc `asyncio.Lock` serialises within the process. The unique indexes (`uq_history_updates_doc_version`, `uq_history_chunks_open`) already prevent corruption. Documented single-instance assumption; multi-instance retry is out of scope for a refactor. |
| Capture (36) | Orphaned blobs if a flush/commit fails after `store.put` | **SKIP** — only occurs on a DB failure *after* a blob write (rare); a full orphan-blob GC is net-new machinery beyond a refactor's risk budget. Noted for a future storage spec. |
| API (37) | `get_diff` reconstructs both texts **before** the size guard | **SKIP** — there is no stored per-version text size to cheaply pre-check; reconstruction is bounded by chunking and the expensive *diff* itself is guarded. Low value/high-fiddliness. |
| API (37) | Restoring to the *current* text produces a near-empty no-op version | **SKIP** — `replace_text` is a real no-op on identical text, but the buffered update is still recorded as a new (identical-content) version, which is consistent with the documented "restore always creates a new version" contract and is non-destructive. Short-circuiting would change that contract. |
| API (37) | `create_label` doesn't verify the version exists | **SKIP** — a label on a non-existent version is harmless (dangling), and versions are sparse after compaction by design; adding a check risks rejecting valid labels on compacted-away versions. |
| Verified correct (no change) | Authz matrix (every history route guarded; cross-project `doc_id`/`label_id` → 404), email enqueue-not-inline + retry + worker registration of `send_email_job`/`sweep_notifications` (incl. hourly cron), notification ownership 404 + sweep idempotency, pagination termination over gaps, hash de-dupe (drops only immediate replays), compaction idempotency/atomicity | **SKIP** — audited and confirmed correct; existing tests already cover these (`test_authz_guard_coverage`, `test_email_job`, `test_notifications_*`, `test_history_*`). |

## Outcomes

- **Restore correctness:** restore is now atomic on the failure paths it can control — a duplicate
  label or unreachable room changes nothing and broadcasts nothing; the broadcast is the last step,
  so live clients never observe an unrecorded restore. No restorable version is ever removed.
- **Storage bloat:** the payload/blob XOR is now DB-enforced (prevents silent corruption that would
  bloat *and* break reconstruction); chunk sealing at `history_chunk_max_updates` and the expiry
  sweep (`sweep_notifications`, hourly cron) were verified wired; invite de-dupe prevents duplicate
  notification rows. Orphan-blob GC was deferred (documented).
- **Email reliability:** confirmed email is only ever enqueued (never inline), `send_email_job`
  re-raises for ARQ retry, and no test tier opens a real SMTP connection; added HTML-escaping.
- **No public API/route contract changed.** No access-control rule weakened.
