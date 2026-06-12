/** Agent chat API calls (spec 46 → spec-44 endpoints). */
import { apiClient } from "@/lib/api-client";
import { config } from "@/config";
import { tokenStore } from "@/lib/token-store";

import type { ChatSession, WireDiffSummary, WireMessage } from "./types";

const base = (projectId: string) => `/api/v1/projects/${projectId}/agent`;

interface WireSession {
  id: string;
  project_id: string;
  title: string | null;
  run_state: string;
  created_at: string;
  updated_at: string;
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
}

export async function getSession(projectId: string, sessionId: string): Promise<SessionDetail> {
  const wire = await apiClient.get<{
    session: WireSession;
    messages: WireMessage[];
    diffs: WireDiffSummary[];
  }>(`${base(projectId)}/sessions/${sessionId}`);
  return { session: toSession(wire.session), messages: wire.messages, diffs: wire.diffs };
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
  const wire = await apiClient.post<{ run_id: string; stream_url: string }>(
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
