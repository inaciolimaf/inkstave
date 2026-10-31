/** The steps of a review outside React: initial load, counts, apply plan, apply (spec 47). */
import { blockedAgainst, rebaseHunks } from "./hunks";
import type { ApplyFileResult, ApplyPhase, DiffProposal, DocumentBridge, FileReviewState } from "./types";

/** Hunk id → accepted, per file path. */
export type Decisions = Record<string, Record<string, boolean>>;

type ProposedFile = DiffProposal["files"][number];

function acceptedHunks(file: ProposedFile, decisions: Decisions): Set<string> {
  return new Set(file.hunks.filter((h) => decisions[file.path]?.[h.id]).map((h) => h.id));
}

/** Defaults every hunk to accepted and evaluates drift against live content. */
export async function loadReview(proposal: DiffProposal, bridge: DocumentBridge) {
  const decisions: Decisions = {};
  const files: Record<string, FileReviewState> = {};
  const liveContent: Record<string, string> = {};
  for (const file of proposal.files) {
    decisions[file.path] = Object.fromEntries(file.hunks.map((h) => [h.id, true]));
    const live = (await bridge.readContent(file.path)) ?? "";
    const blocked = blockedAgainst(live, file.hunks);
    liveContent[file.path] = live;
    files[file.path] = {
      path: file.path,
      baseVersion: file.baseVersion,
      decisions: decisions[file.path],
      baseChanged: blocked.length > 0,
      blockedHunkIds: blocked,
    };
  }
  return { decisions, files, liveContent };
}

export function countHunks(proposal: DiffProposal | null, decisions: Decisions) {
  let accepted = 0;
  let total = 0;
  for (const file of proposal?.files ?? []) {
    total += file.hunks.length;
    accepted += file.hunks.filter((h) => decisions[file.path]?.[h.id]).length;
  }
  return { accepted, total };
}

/** What a confirmed apply would do (applicable accepted hunks vs blocked). */
export function planApply(
  proposal: DiffProposal | null,
  decisions: Decisions,
  liveContent: Record<string, string>,
) {
  let applicable = 0;
  let blocked = 0;
  let fileCount = 0;
  for (const file of proposal?.files ?? []) {
    const r = rebaseHunks(liveContent[file.path] ?? "", file.hunks, acceptedHunks(file, decisions));
    if (r.appliedHunkIds.length > 0) fileCount += 1;
    applicable += r.appliedHunkIds.length;
    blocked += r.blockedHunkIds.length;
  }
  return { fileCount, applicable, blocked };
}

/** Rebases the accepted hunks on each file's current text and writes them through the bridge. */
export async function applyProposal(
  proposal: DiffProposal,
  decisions: Decisions,
  bridge: DocumentBridge,
): Promise<{ phase: ApplyPhase; results: ApplyFileResult[] }> {
  const results: ApplyFileResult[] = [];
  for (const file of proposal.files) {
    const accepted = acceptedHunks(file, decisions);
    try {
      const live = (await bridge.readContent(file.path)) ?? "";
      const r = rebaseHunks(live, file.hunks, accepted);
      if (r.appliedHunkIds.length > 0) await bridge.applyContent(file.path, r.target);
      results.push({
        path: file.path,
        appliedHunks: r.appliedHunkIds,
        blockedHunks: r.blockedHunkIds,
      });
    } catch (err) {
      results.push({ path: file.path, appliedHunks: [], blockedHunks: [], error: String(err) });
    }
  }
  return { phase: results.some((r) => r.error) ? "error" : "applied", results };
}
