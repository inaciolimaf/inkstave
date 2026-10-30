/** Fetch a proposal's full diff via the spec-44 diffs endpoint (spec 47). */
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
