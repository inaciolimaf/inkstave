/** The diff-review API: a proposal's hunks (spec 47) and the user's decision on them (spec 110). */
import type { Schemas } from "@/api/models";
import { apiClient } from "@/lib/api-client";

import { mapWireHunk, type WireHunk } from "./hunks";
import type { DiffProposal } from "./types";

/** The backend types `hunks` as loose objects; `WireHunk` is what it writes. */
type WireDiff = Omit<Schemas["ProposedDiffSummary"], "hunks"> & { hunks?: WireHunk[] | null };

/** Load the single-file proposal identified by `proposalId` from the session's diffs. */
export async function fetchProposal(
  projectId: string,
  sessionId: string,
  proposalId: string,
): Promise<DiffProposal | null> {
  const rows = await apiClient.get<WireDiff[]>(
    `/api/v1/projects/${projectId}/agent/sessions/${sessionId}/diffs?include=hunks`,
  );
  const row = rows.find((r) => r.id === proposalId);
  if (!row) return null;
  return {
    id: row.id,
    projectId,
    sessionId,
    status: row.status,
    createdAt: row.created_at,
    files: [
      {
        path: row.path,
        docId: row.doc_id,
        baseVersion: row.base_version,
        hunks: (row.hunks ?? []).map(mapWireHunk),
      },
    ],
  };
}

/** The hunk ids the user accepted, rejected, or found no longer applicable (stale). */
export interface DecisionLists {
  accepted: string[];
  rejected: string[];
  stale: string[];
}

/** Record the decision once; resolves with the proposal's new status (spec 110). */
export async function recordDecision(
  projectId: string,
  sessionId: string,
  proposalId: string,
  lists: DecisionLists,
): Promise<string> {
  const row = await apiClient.post<{ status: string }>(
    `/api/v1/projects/${projectId}/agent/sessions/${sessionId}/diffs/${proposalId}/outcome`,
    lists,
  );
  return row.status;
}
