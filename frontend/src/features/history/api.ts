/** History API calls (spec 38 → spec-37 endpoints). snake_case ↔ camelCase here only. */
import { ApiError, apiClient } from "@/lib/api-client";

import type {
  DiffHunk,
  DiffResult,
  HistoryLabel,
  RestoreResult,
  Version,
  VersionsPage,
} from "./types";

const base = (projectId: string, docId: string) =>
  `/api/v1/projects/${projectId}/docs/${docId}/history`;

interface VersionWire {
  version: number;
  timestamp: string;
  author: { id: string; name: string; email: string } | null;
  op_count: number;
  size: number;
  labels: { id: string; name: string }[];
}

function toVersion(w: VersionWire): Version {
  return {
    version: w.version,
    timestamp: w.timestamp,
    author: w.author,
    opCount: w.op_count,
    size: w.size,
    labels: w.labels,
  };
}

export async function listVersions(
  projectId: string,
  docId: string,
  opts: { before?: number; limit?: number } = {},
): Promise<VersionsPage> {
  const params = new URLSearchParams();
  if (opts.before !== undefined) params.set("before", String(opts.before));
  if (opts.limit !== undefined) params.set("limit", String(opts.limit));
  const qs = params.toString();
  const wire = await apiClient.get<{
    doc_id: string;
    current_version: number;
    versions: VersionWire[];
    has_more: boolean;
    next_before: number | null;
  }>(`${base(projectId, docId)}/versions${qs ? `?${qs}` : ""}`);
  return {
    docId: wire.doc_id,
    currentVersion: wire.current_version,
    versions: wire.versions.map(toVersion),
    hasMore: wire.has_more,
    nextBefore: wire.next_before,
  };
}

interface DiffHunkWire {
  old_start: number;
  old_lines: number;
  new_start: number;
  new_lines: number;
  segments: { type: "context" | "added" | "removed"; value: string }[];
}

function toHunk(w: DiffHunkWire): DiffHunk {
  return {
    oldStart: w.old_start,
    oldLines: w.old_lines,
    newStart: w.new_start,
    newLines: w.new_lines,
    segments: w.segments,
  };
}

export async function getDiff(
  projectId: string,
  docId: string,
  from: number,
  to: number | "current",
): Promise<DiffResult> {
  let wire: {
    from: number;
    to: number | "current";
    binary: boolean;
    too_large: boolean;
    hunks: DiffHunkWire[];
  };
  try {
    wire = await apiClient.get(`${base(projectId, docId)}/diff?from=${from}&to=${to}`);
  } catch (err) {
    // The diff route signals "too large" with HTTP 413 carrying the full diff
    // body, but `apiClient` throws on any non-ok status. Map that one case to a
    // structured result so `HistoryDiffView` can render its "too large" branch;
    // re-throw everything else unchanged.
    if (err instanceof ApiError && err.status === 413) {
      return { from, to, binary: false, tooLarge: true, hunks: [] };
    }
    throw err;
  }
  return {
    from: wire.from,
    to: wire.to,
    binary: wire.binary,
    tooLarge: wire.too_large,
    hunks: wire.hunks.map(toHunk),
  };
}

interface LabelWire {
  id: string;
  name: string;
  version: number;
  doc_id: string | null;
  created_by: string | null;
  created_at: string;
}

function toLabel(w: LabelWire): HistoryLabel {
  return {
    id: w.id,
    name: w.name,
    version: w.version,
    docId: w.doc_id,
    createdBy: w.created_by,
    createdAt: w.created_at,
  };
}

export async function listLabels(projectId: string, docId: string): Promise<HistoryLabel[]> {
  const wire = await apiClient.get<LabelWire[]>(`${base(projectId, docId)}/labels`);
  return wire.map(toLabel);
}

export async function createLabel(
  projectId: string,
  docId: string,
  version: number,
  name: string,
): Promise<HistoryLabel> {
  return toLabel(
    await apiClient.post<LabelWire>(`${base(projectId, docId)}/labels`, { version, name }),
  );
}

export async function deleteLabel(
  projectId: string,
  docId: string,
  labelId: string,
): Promise<void> {
  await apiClient.delete(`${base(projectId, docId)}/labels/${labelId}`);
}

export async function restoreVersion(
  projectId: string,
  docId: string,
  version: number,
  labelName?: string,
): Promise<RestoreResult> {
  const wire = await apiClient.post<{
    doc_id: string;
    restored_from_version: number;
    new_version: number;
    label: LabelWire | null;
  }>(`${base(projectId, docId)}/restore`, { version, label_name: labelName });
  return {
    docId: wire.doc_id,
    restoredFromVersion: wire.restored_from_version,
    newVersion: wire.new_version,
    label: wire.label ? toLabel(wire.label) : null,
  };
}
