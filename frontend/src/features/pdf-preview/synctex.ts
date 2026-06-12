/**
 * SyncTeX source <-> PDF API client + types (spec 26).
 *
 * Location note (deviation from spec 26 §5.3): the spec places this API client at
 * `src/lib/api/synctex.ts`. It is deliberately co-located here under
 * `features/pdf-preview/` instead, beside its only consumers (the PDF preview /
 * sync-jump code), following this codebase's feature-colocation convention. This
 * is a knowing, low-risk deviation: the module is functionally identical wherever
 * it lives, and keeping it next to its callers avoids a cross-feature import hop.
 */
import { ApiError, apiClient } from "@/lib/api-client";

export interface SyncTexBox {
  page: number;
  h: number;
  v: number;
  width: number;
  height: number;
  depth: number;
}

export interface ForwardResult {
  boxes: SyncTexBox[];
}

export interface InverseResult {
  file: string;
  line: number;
  column: number | null;
}

/** Why a sync request did not yield a location — a discriminated failure. */
export type SyncReason = "no_match" | "synctex_unavailable" | "error";

export type SyncResult<T> = { ok: true; value: T } | { ok: false; reason: SyncReason };

function base(projectId: string): string {
  return `/api/v1/projects/${projectId}/synctex`;
}

/** Map a thrown error to a sync failure reason (the backend's 404 discriminants). */
export function reasonFromError(err: unknown): SyncReason {
  if (err instanceof ApiError && err.status === 404) {
    return err.detail === "synctex_unavailable" ? "synctex_unavailable" : "no_match";
  }
  return "error";
}

/** Forward sync: source file + line -> PDF boxes. */
export async function codeToPdf(
  projectId: string,
  input: { file: string; line: number; column?: number; compileId?: string },
): Promise<SyncResult<ForwardResult>> {
  const params = new URLSearchParams({ file: input.file, line: String(input.line) });
  if (input.column != null) params.set("column", String(input.column));
  if (input.compileId) params.set("compile_id", input.compileId);
  try {
    const value = await apiClient.get<ForwardResult>(`${base(projectId)}/code-to-pdf?${params}`);
    return { ok: true, value };
  } catch (err) {
    return { ok: false, reason: reasonFromError(err) };
  }
}

/** Inverse sync: PDF page + point -> source location. */
export async function pdfToCode(
  projectId: string,
  input: { page: number; h: number; v: number; compileId?: string },
): Promise<SyncResult<InverseResult>> {
  const params = new URLSearchParams({
    page: String(input.page),
    h: String(input.h),
    v: String(input.v),
  });
  if (input.compileId) params.set("compile_id", input.compileId);
  try {
    const value = await apiClient.get<InverseResult>(`${base(projectId)}/pdf-to-code?${params}`);
    return { ok: true, value };
  } catch (err) {
    return { ok: false, reason: reasonFromError(err) };
  }
}
