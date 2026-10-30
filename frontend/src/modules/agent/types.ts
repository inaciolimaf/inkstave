/** Frontend types mirroring the spec-44 agent contract (spec 46). */
import type { Schemas } from "@/api/models";

export type ChatRole = "user" | "assistant";

/** Server-contract shape of an agent chat session (spec 46 §5.1). */
export interface ChatSession {
  id: string;
  projectId: string;
  title: string | null;
  createdAt: string;
  updatedAt: string;
  /**
   * Non-contract runtime state. NOT part of the spec-46 server contract; kept
   * optional only because some runtime code annotates a transient run state on
   * the session. Prefer {@link ChatSessionRuntimeState} for new runtime usage.
   */
  runState?: string;
}

/** Client-only runtime state layered on top of the server {@link ChatSession}. */
export interface ChatSessionRuntimeState {
  runState: string;
}

export type TranscriptItem =
  | {
      kind: "message";
      id: string;
      role: ChatRole;
      text: string;
      status: "streaming" | "complete" | "cancelled" | "error";
    }
  | {
      kind: "tool";
      id: string;
      name: string;
      args: unknown;
      result?: unknown;
      status: "running" | "ok" | "error";
      errorText?: string;
    }
  | {
      kind: "diff-proposal";
      id: string;
      proposalId: string;
      files: { path: string; hunkCount: number }[];
    }
  | { kind: "error"; id: string; code: string; message: string; retryable: boolean };

export type RunPhase = "idle" | "starting" | "streaming" | "stopping" | "done" | "error" | "cancelled";

export interface AgentRunState {
  sessionId: string | null;
  runId: string | null;
  phase: RunPhase;
  items: TranscriptItem[];
  error?: { code: string; message: string; retryable: boolean };
  /** Internal: spec-44 event `seq`s already applied (idempotent reducer). */
  seenSeqs: number[];
}

/** A spec-44 SSE event envelope. */
export interface AgentEvent {
  type: string;
  run_id?: string;
  seq?: number;
  ts?: string;
  text?: string;
  tool_call_id?: string;
  name?: string;
  arguments?: unknown;
  ok?: boolean;
  summary?: string;
  diff_id?: string;
  doc_id?: string;
  path?: string;
  stats?: { hunk_count?: number; additions?: number; deletions?: number };
  usage?: Record<string, number>;
  iterations?: number;
  final_text?: string | null;
  code?: string;
  message?: string;
}

/** The backend types `tool_calls` as loose objects; these are the fields the agent writes. */
export type WireMessage = Pick<
  Schemas["AgentMessageOut"],
  "id" | "seq" | "role" | "content" | "tool_call_id"
> & { tool_calls: { id: string; name: string; arguments: Record<string, unknown> }[] | null };

export type WireDiffSummary = Pick<Schemas["ProposedDiffSummary"], "id" | "doc_id" | "path" | "status"> & {
  stats: { hunk_count?: number };
};
