/** Compile + output API calls for the PDF preview (specs 22/23). */
import { apiClient } from "@/lib/api-client";
import { config } from "@/config";
import { tokenStore } from "@/lib/token-store";

import type { CompileStatus } from "./types";

function base(projectId: string): string {
  return `/api/v1/projects/${projectId}/compile`;
}

/** Enqueue a compile (spec 22). Returns the initial (usually `queued`) status. */
export function requestCompile(
  projectId: string,
  options: { mainFile?: string; force?: boolean } = {},
): Promise<CompileStatus> {
  return apiClient.post<CompileStatus>(base(projectId), {
    main_file: options.mainFile ?? null,
    force: options.force ?? false,
  });
}

/** Fetch a status snapshot for one compile (spec 22) — the polling fallback. */
export function getCompile(projectId: string, compileId: string): Promise<CompileStatus> {
  return apiClient.get<CompileStatus>(`${base(projectId)}/${compileId}`);
}

/** Fetch the most recent compile, if any (spec 22). */
export function getLatestCompile(projectId: string): Promise<CompileStatus> {
  return apiClient.get<CompileStatus>(`${base(projectId)}/latest`);
}

/** Request cancellation of an in-flight compile (spec 22). */
export function cancelCompile(projectId: string, compileId: string): Promise<CompileStatus> {
  return apiClient.post<CompileStatus>(`${base(projectId)}/${compileId}/cancel`);
}

/** Fetch the raw compile log text (spec 23). */
export function getCompileLog(projectId: string, compileId: string): Promise<string> {
  return apiClient.getText(`${base(projectId)}/${compileId}/output.log`);
}

/**
 * Fetch the compiled PDF as an `ArrayBuffer` (spec 23).
 *
 * We fetch the full bytes through the authed API client rather than letting
 * PDF.js fetch the URL directly, because the access token lives in memory and
 * PDF.js's range fetcher can't carry our `Authorization` header. See
 * `docs/adr/0024-pdf-preview.md`.
 */
export function getCompilePdf(projectId: string, compileId: string): Promise<ArrayBuffer> {
  return apiClient.getBytes(`${base(projectId)}/${compileId}/output.pdf`);
}

/** Absolute URL for the live SSE status stream, carrying the token as a query param. */
export function compileEventsUrl(projectId: string, compileId: string): string {
  const token = tokenStore.getAccessToken();
  const query = token ? `?access_token=${encodeURIComponent(token)}` : "";
  return `${config.apiBaseUrl}${base(projectId)}/${compileId}/events${query}`;
}
