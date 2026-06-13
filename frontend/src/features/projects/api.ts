/** Project API calls (spec 11). snake_case ↔ camelCase mapping lives here only. */
import { config } from "@/config";
import { apiClient } from "@/lib/api-client";
import { sanitizeDownloadName, triggerBrowserDownload } from "@/lib/download";
import { tokenStore } from "@/lib/token-store";

import type { Project } from "./types";

interface ProjectWire {
  id: string;
  name: string;
  owner_id: string;
  root_doc_id: string | null;
  created_at: string;
  updated_at: string;
}

interface ProjectListWire {
  items: ProjectWire[];
  total: number;
}

function toProject(wire: ProjectWire): Project {
  return {
    id: wire.id,
    name: wire.name,
    ownerId: wire.owner_id,
    createdAt: wire.created_at,
    updatedAt: wire.updated_at,
  };
}

export async function listProjects(): Promise<Project[]> {
  const data = await apiClient.get<ProjectListWire>("/api/v1/projects?limit=100");
  return data.items.map(toProject);
}

export async function getProject(id: string): Promise<Project> {
  return toProject(await apiClient.get<ProjectWire>(`/api/v1/projects/${id}`));
}

export async function createProject(name: string): Promise<Project> {
  return toProject(await apiClient.post<ProjectWire>("/api/v1/projects", { name }));
}

export async function renameProject(id: string, name: string): Promise<Project> {
  return toProject(await apiClient.patch<ProjectWire>(`/api/v1/projects/${id}`, { name }));
}

export async function deleteProject(id: string): Promise<void> {
  await apiClient.delete(`/api/v1/projects/${id}`);
}

// --------------------------------------------------------------------------- //
// Project import from a .zip archive (spec 101)
// --------------------------------------------------------------------------- //

export type ImportStatus = "queued" | "running" | "success" | "partial" | "failure" | "error";

export interface ProjectImport {
  importId: string;
  projectId: string;
  status: ImportStatus;
  entriesTotal: number | null;
  entriesImported: number | null;
  errorType: string | null;
  errorMessage: string | null;
}

interface ProjectImportWire {
  import_id: string;
  project_id: string;
  status: ImportStatus;
  entries_total: number | null;
  entries_imported: number | null;
  error_type: string | null;
  error_message: string | null;
}

function toImport(wire: ProjectImportWire): ProjectImport {
  return {
    importId: wire.import_id,
    projectId: wire.project_id,
    status: wire.status,
    entriesTotal: wire.entries_total,
    entriesImported: wire.entries_imported,
    errorType: wire.error_type,
    errorMessage: wire.error_message,
  };
}

/** A failed import upload, carrying the machine-readable `error_type` for i18n mapping. */
export class ImportUploadError extends Error {
  readonly status: number;
  readonly errorType: string | null;

  constructor(status: number, errorType: string | null, message: string) {
    super(message);
    this.name = "ImportUploadError";
    this.status = status;
    this.errorType = errorType;
  }
}

/**
 * Upload a `.zip` to create a new project, reporting upload progress.
 *
 * The shared {@link apiClient} is JSON-only, so multipart + progress goes through
 * `XMLHttpRequest` here (the only place), keeping the Bearer-token handling
 * identical. Resolves with the `202` import row; rejects with {@link ImportUploadError}.
 */
export function importProjectZip(
  file: File,
  name?: string,
  onProgress?: (fraction: number) => void,
): Promise<ProjectImport> {
  const form = new FormData();
  form.append("file", file);
  if (name && name.trim()) form.append("name", name.trim());

  return new Promise<ProjectImport>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${config.apiBaseUrl}/api/v1/projects/import`);
    const access = tokenStore.getAccessToken();
    if (access) xhr.setRequestHeader("Authorization", `Bearer ${access}`);

    xhr.upload.onprogress = (event) => {
      if (onProgress && event.lengthComputable) onProgress(event.loaded / event.total);
    };
    xhr.onerror = () =>
      reject(new ImportUploadError(0, "upload_failed", "Network error during upload"));
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        onProgress?.(1);
        resolve(toImport(JSON.parse(xhr.responseText) as ProjectImportWire));
        return;
      }
      let errorType: string | null = null;
      let message = `Upload failed (${xhr.status})`;
      try {
        const body = JSON.parse(xhr.responseText) as {
          error?: { type?: string; message?: string };
        };
        errorType = body.error?.type ?? null;
        message = body.error?.message ?? message;
      } catch {
        // Non-JSON body — keep the status message.
      }
      reject(new ImportUploadError(xhr.status, errorType, message));
    };
    xhr.send(form);
  });
}

export async function getImportStatus(projectId: string, importId: string): Promise<ProjectImport> {
  return toImport(
    await apiClient.get<ProjectImportWire>(`/api/v1/projects/${projectId}/import/${importId}`),
  );
}

// --------------------------------------------------------------------------- //
// Project export to a .zip archive (spec 102)
// --------------------------------------------------------------------------- //

/** Fetch the project's .zip (authed, refresh-aware) and trigger a browser download. */
export async function downloadProjectZip(id: string, name: string): Promise<void> {
  const buf = await apiClient.getBytes(`/api/v1/projects/${id}/export.zip`);
  const blob = new Blob([buf], { type: "application/zip" });
  triggerBrowserDownload(blob, `${sanitizeDownloadName(name)}.zip`);
}
