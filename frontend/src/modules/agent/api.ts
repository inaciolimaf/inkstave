/** Agent chat API calls (spec 46 → spec-44 endpoints). */
import type { Schemas } from "@/api/models";
import { apiClient } from "@/lib/api-client";
import { config } from "@/config";
import { tokenStore } from "@/lib/token-store";

import type { ChatSession, FileOp, WireDiffSummary, WireMessage } from "./types";

const base = (projectId: string) => `/api/v1/projects/${projectId}/agent`;

type WireSession = Schemas["AgentSessionOut"];
export type WireFileOp = Schemas["ProposedFileOpOut"];

export function toFileOp(w: WireFileOp): FileOp {
  return {
    opId: w.id,
    opKind: w.kind,
    entityType: w.entity_type,
    path: w.path,
    newPath: w.new_path,
    affectedPaths: w.affected_paths,
    status: w.status,
    rationale: w.rationale,
  };
}

function toSession(w: WireSession): ChatSession {
  return {
    id: w.id,
    projectId: w.project_id,
    title: w.title,
    runState: w.run_state,
    createdAt: w.created_at,
    updatedAt: w.updated_at,
  };
}

export async function listSessions(projectId: string): Promise<ChatSession[]> {
  const wire = await apiClient.get<WireSession[]>(`${base(projectId)}/sessions`);
  return wire.map(toSession);
}

export async function createSession(projectId: string, title?: string): Promise<ChatSession> {
  return toSession(
    await apiClient.post<WireSession>(`${base(projectId)}/sessions`, { title: title ?? null }),
  );
}

export interface SessionDetail {
  session: ChatSession;
  messages: WireMessage[];
  diffs: WireDiffSummary[];
  file_ops: WireFileOp[];
}

export async function getSession(projectId: string, sessionId: string): Promise<SessionDetail> {
  const wire = await apiClient.get<Schemas["SessionDetailOut"]>(`${base(projectId)}/sessions/${sessionId}`);
  return {
    session: toSession(wire.session),
    messages: wire.messages as WireMessage[],
    diffs: wire.diffs as WireDiffSummary[],
    file_ops: wire.file_ops,
  };
}

export interface StartRunResult {
  runId: string;
  streamUrl: string;
}

export async function startRun(
  projectId: string,
  sessionId: string,
  content: string,
): Promise<StartRunResult> {
  const wire = await apiClient.post<Schemas["PostMessageOut"]>(
    `${base(projectId)}/sessions/${sessionId}/messages`,
    { content },
  );
  return { runId: wire.run_id, streamUrl: wire.stream_url };
}

export async function stopRun(projectId: string, sessionId: string, runId: string): Promise<void> {
  await apiClient.post(`${base(projectId)}/sessions/${sessionId}/runs/${runId}/cancel`, {});
}

/** Absolute SSE URL carrying the JWT as a query param (EventSource can't set headers). */
export function runEventsUrl(projectId: string, sessionId: string, runId: string): string {
  const token = tokenStore.getAccessToken();
  const query = token ? `?access_token=${encodeURIComponent(token)}` : "";
  return `${config.apiBaseUrl}${base(projectId)}/sessions/${sessionId}/runs/${runId}/events${query}`;
}

const fileOps = (projectId: string, sessionId: string) => `${base(projectId)}/sessions/${sessionId}/file-ops`;

/** The content of a proposed document, which the session detail leaves out. */
export async function fetchFileOpContent(projectId: string, sessionId: string, opId: string) {
  const rows = await apiClient.get<WireFileOp[]>(fileOps(projectId, sessionId));
  return rows.find((row) => row.id === opId)?.content ?? "";
}

export async function decideFileOp(
  projectId: string,
  sessionId: string,
  opId: string,
  decision: "apply" | "reject",
): Promise<FileOp> {
  const wire = await apiClient.post<WireFileOp>(`${fileOps(projectId, sessionId)}/${opId}/${decision}`);
  return toFileOp(wire);
}
