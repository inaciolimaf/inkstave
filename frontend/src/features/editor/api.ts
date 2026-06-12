/** Document content API (spec 13). Wire mapping lives here. */
import { ApiError, apiClient } from "@/lib/api-client";

import type { DocumentContent } from "./types";

interface DocumentWire {
  entity_id: string;
  project_id: string;
  version: number;
  size_bytes: number;
  content: string;
  updated_at: string;
  // The backend `DocumentContentRead` wire currently omits `name` (spec 73
  // reports this gap to the pack that owns the document schema). Mapped through
  // when present so the frontend contract matches spec 18 §5.1.
  name?: string;
}

export interface ConflictInfo {
  currentVersion: number;
  currentContent: string;
}

/** Thrown when a versioned save loses to a newer server version (spec 13's 409). */
export class VersionConflictError extends Error {
  constructor(public readonly conflict: ConflictInfo) {
    super("version_conflict");
    this.name = "VersionConflictError";
  }
}

export async function getDocument(projectId: string, docId: string): Promise<DocumentContent> {
  const wire = await apiClient.get<DocumentWire>(
    `/api/v1/projects/${projectId}/documents/${docId}`,
  );
  return { id: wire.entity_id, name: wire.name, content: wire.content, version: wire.version };
}

/**
 * Replace a document's content with optimistic concurrency (spec 13).
 * Returns the new version on success; throws {@link VersionConflictError} on 409
 * (carrying the server's current version + content from the error envelope).
 */
export async function saveDocument(
  projectId: string,
  docId: string,
  content: string,
  baseVersion: number,
): Promise<{ version: number }> {
  try {
    const wire = await apiClient.put<DocumentWire>(
      `/api/v1/projects/${projectId}/documents/${docId}`,
      { content, base_version: baseVersion },
    );
    return { version: wire.version };
  } catch (err) {
    if (err instanceof ApiError && err.status === 409) {
      const detail = (err.details?.[0] ?? {}) as {
        current_version?: number;
        current_content?: string;
      };
      throw new VersionConflictError({
        currentVersion: detail.current_version ?? baseVersion,
        currentContent: detail.current_content ?? "",
      });
    }
    throw err;
  }
}
