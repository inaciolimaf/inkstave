/** PDF-preview feature types (spec 24). Mirrors the spec-22 compile schemas. */
import type { Schemas } from "@/api/models";

/** Job lifecycle states, mirroring the backend `CompileJobStatus` enum (spec 22). */
export type CompileJobStatus =
  "queued" | "running" | "success" | "failure" | "timeout" | "cancelled" | "error";

/** The local compile state machine: `idle` plus every backend status. */
export type CompileState = "idle" | CompileJobStatus;

/** A manifest entry describing one stored artifact (subset we care about here). */
export interface CompileArtifact {
  name: string;
  rel_path: string;
  size_bytes: number;
  content_type: string;
}

/** The backend types `status` and the manifest loosely; these are the values it produces. */
export type CompileStatus = Omit<Schemas["CompileStatusResponse"], "status" | "artifact_manifest"> & {
  status: CompileJobStatus;
  artifact_manifest?: CompileArtifact[] | null;
};

export const TERMINAL_STATUSES: ReadonlySet<CompileJobStatus> = new Set([
  "success",
  "failure",
  "timeout",
  "cancelled",
  "error",
]);

export const ACTIVE_STATES: ReadonlySet<CompileState> = new Set<CompileState>(["queued", "running"]);

export function isTerminal(status: CompileJobStatus): boolean {
  return TERMINAL_STATUSES.has(status);
}

export function isActive(state: CompileState): boolean {
  return ACTIVE_STATES.has(state);
}
