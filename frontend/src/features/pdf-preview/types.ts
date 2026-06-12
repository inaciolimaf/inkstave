/** PDF-preview feature types (spec 24). Mirrors the spec-22 compile schemas. */

/** Job lifecycle states, mirroring the backend `CompileJobStatus` enum (spec 22). */
export type CompileJobStatus =
  | "queued"
  | "running"
  | "success"
  | "failure"
  | "timeout"
  | "cancelled"
  | "error";

/** The local compile state machine: `idle` plus every backend status. */
export type CompileState = "idle" | CompileJobStatus;

/** A manifest entry describing one stored artifact (subset we care about here). */
export interface CompileArtifact {
  name: string;
  rel_path: string;
  size_bytes: number;
  content_type: string;
}

/** Status snapshot returned by `POST /compile`, `GET /compile/{id}`, and SSE. */
export interface CompileStatus {
  id: string;
  project_id: string;
  status: CompileJobStatus;
  main_file: string;
  has_pdf: boolean;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  exit_code: number | null;
  error_message: string | null;
  log_excerpt: string | null;
  artifact_manifest: CompileArtifact[] | null;
}

export const TERMINAL_STATUSES: ReadonlySet<CompileJobStatus> = new Set([
  "success",
  "failure",
  "timeout",
  "cancelled",
  "error",
]);

export const ACTIVE_STATES: ReadonlySet<CompileState> = new Set<CompileState>([
  "queued",
  "running",
]);

export function isTerminal(status: CompileJobStatus): boolean {
  return TERMINAL_STATUSES.has(status);
}

export function isActive(state: CompileState): boolean {
  return ACTIVE_STATES.has(state);
}
