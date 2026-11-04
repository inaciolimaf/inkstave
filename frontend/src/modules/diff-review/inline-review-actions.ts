/**
 * What a decision does (spec 110): an accepted hunk is written through the CRDT, one minimal edit per write,
 * and once every hunk is decided the outcome is recorded and the review closes. Nothing else changes the text.
 */
import type { EditorView } from "@codemirror/view";

import { ApiError } from "@/lib/api-client";

import type { DecisionLists } from "./api";
import { rebaseHunks } from "./hunks";
import {
  type HunkPatch,
  type InlineReview,
  inlineReviewField,
  stopInlineReview,
  updateHunk,
} from "./inline-review-extension";
import {
  type Decision,
  type ReviewActions,
  type ReviewSnapshot,
  allDecided,
  outcomeLists,
  pendingHunks,
} from "./inline-review-model";

export type ReviewNotice = "acceptError" | "saveError" | "drifted";

export interface ReviewDeps {
  /** The editor showing this review's document, or null when another document is open. */
  view(): EditorView | null;
  readLive(path: string): Promise<string>;
  write(path: string, target: string): Promise<void>;
  /** Records the decision; resolves with the proposal's new status. */
  record(proposalId: string, lists: DecisionLists): Promise<string>;
  notify(notice: ReviewNotice): void;
  /** The proposal was decided: its status is now known. */
  finished(proposalId: string, status: string): void;
  /** The review ended on this view. */
  closed(): void;
  /** The review changed; its decisions are remembered and its bar updated. */
  changed(review: ReviewSnapshot): void;
}

type Entry = [hunkId: string, decision: Decision];

function storedStatus(err: ApiError): string | undefined {
  const first = err.details?.[0];
  return typeof first === "object" && first !== null && "status" in first ? String(first.status) : undefined;
}

/**
 * Writes the hunks among `ids` that still apply to the live text, as one edit. Returns the ids written.
 * The rebase runs on the live text, so a hunk that no longer matches is skipped, not forced.
 */
async function writeHunks(deps: ReviewDeps, review: InlineReview, ids: string[]): Promise<Set<string>> {
  const live = await deps.readLive(review.path);
  const r = rebaseHunks(
    live,
    review.hunks.map((h) => h.hunk),
    new Set(ids),
  );
  if (r.appliedHunkIds.length > 0) await deps.write(review.path, r.target);
  return new Set(r.appliedHunkIds);
}

export function createReviewActions(deps: ReviewDeps): ReviewActions {
  const current = (): InlineReview | null => deps.view()?.state.field(inlineReviewField) ?? null;
  const find = (review: InlineReview | null, hunkId: string) =>
    review?.hunks.find((h) => h.hunk.id === hunkId);
  const openOf = (review: InlineReview) => pendingHunks(review.hunks).filter((h) => !h.busy);

  const patchEach = (entries: [string, HunkPatch["patch"]][]) => {
    if (entries.length === 0) return;
    deps.view()?.dispatch({ effects: entries.map(([hunkId, patch]) => updateHunk.of({ hunkId, patch })) });
  };
  const decide = (entries: Entry[]) =>
    patchEach(entries.map(([id, decision]) => [id, { decision, busy: false }]));
  const setBusy = (ids: string[], busy: boolean) => patchEach(ids.map((id) => [id, { busy }]));

  const close = () => {
    deps.view()?.dispatch({ effects: stopInlineReview.of(null) });
    deps.closed();
  };

  const settle = async () => {
    const review = current();
    if (!review || review.readOnly || review.hunks.length === 0 || !allDecided(review.hunks)) return;
    try {
      const status = await deps.record(review.proposalId, outcomeLists(review.hunks));
      deps.finished(review.proposalId, status);
      close();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        const status = storedStatus(err);
        if (status) deps.finished(review.proposalId, status);
        close();
        return;
      }
      deps.notify("saveError");
    }
  };

  const reject = (hunkId: string) => {
    const hunk = find(current(), hunkId);
    if (!hunk || hunk.decision !== "open" || hunk.busy || current()?.readOnly) return;
    decide([[hunkId, hunk.blocked ? "stale" : "rejected"]]);
    void settle();
  };

  const accept = async (hunkId: string) => {
    const review = current();
    const hunk = find(review, hunkId);
    if (!review || review.readOnly || !hunk || hunk.decision !== "open" || hunk.busy || hunk.blocked) return;
    setBusy([hunkId], true);
    try {
      if (!(await writeHunks(deps, review, [hunkId])).has(hunkId)) {
        patchEach([[hunkId, { busy: false, blocked: true }]]);
        deps.notify("drifted");
        return;
      }
      decide([[hunkId, "accepted"]]);
      void settle();
    } catch {
      setBusy([hunkId], false);
      deps.notify("acceptError");
    }
  };

  const acceptAll = async () => {
    const review = current();
    if (!review || review.readOnly) return;
    const open = openOf(review);
    if (open.length === 0) return;
    const ids = open.map((h) => h.hunk.id);
    setBusy(ids, true);
    try {
      const applied = await writeHunks(
        deps,
        review,
        open.filter((h) => !h.blocked).map((h) => h.hunk.id),
      );
      decide(ids.map((id): Entry => [id, applied.has(id) ? "accepted" : "stale"]));
      void settle();
    } catch {
      setBusy(ids, false);
      deps.notify("acceptError");
    }
  };

  const rejectAll = () => {
    const review = current();
    if (!review || review.readOnly) return;
    const open = openOf(review);
    if (open.length === 0) return;
    decide(open.map((h): Entry => [h.hunk.id, h.blocked ? "stale" : "rejected"]));
    void settle();
  };

  return {
    accept: (hunkId) => void accept(hunkId),
    reject,
    acceptAll: () => void acceptAll(),
    rejectAll,
    settle: () => void settle(),
    close,
    onChange: (review) => deps.changed(review),
  };
}
