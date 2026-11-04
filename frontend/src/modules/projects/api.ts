/** Project API calls (spec 11). snake_case ↔ camelCase mapping lives here only. */
import type { Schemas } from "@/api/models";
import { config } from "@/config";
import { ApiError, apiClient } from "@/lib/api-client";
import { sanitizeDownloadName, triggerBrowserDownload } from "@/lib/download";
import { tokenStore } from "@/lib/token-store";

import type { ListedProject, Project } from "./types";

/** Spell-check languages a project can use (spec 113); the server validates them. */
type SpellcheckLanguage = "off" | "en-US" | "pt-BR";

type ProjectWire = Schemas["ProjectRead"];

type ProjectListWire = Schemas["ProjectList"];

type ProjectListItemWire = Schemas["ProjectListItem"];

function toProject(wire: ProjectWire): Project {
  return {
    id: wire.id,
    name: wire.name,
    ownerId: wire.owner_id,
    rootDocId: wire.root_doc_id,
    spellcheckLanguage: wire.spellcheck_language,
    createdAt: wire.created_at,
    updatedAt: wire.updated_at,
  };
}

function toListedProject(wire: ProjectListItemWire): ListedProject {
  return {
    ...toProject(wire),
    role: wire.role,
    owner: { id: wire.owner.id, displayName: wire.owner.display_name },
  };
}

/** Every project the caller is an active member of; the dashboard filters by role itself. */
export async function listProjects(): Promise<ListedProject[]> {
  const data = await apiClient.get<ProjectListWire>("/api/v1/projects?limit=100");
  return data.items.map(toListedProject);
}

/** A non-owner removes their own membership (spec 33), which takes the project off their list. */
export async function leaveProject(id: string, userId: string): Promise<void> {
  await apiClient.delete(`/api/v1/projects/${id}/members/${userId}`);
}

export async function getProject(id: string): Promise<Project> {
  return toProject(await apiClient.get<ProjectWire>(`/api/v1/projects/${id}`));
}

export async function createProject(name: string, spellcheckLanguage: SpellcheckLanguage): Promise<Project> {
  return toProject(
    await apiClient.post<ProjectWire>("/api/v1/projects", { name, spellcheck_language: spellcheckLanguage }),
  );
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

/** `zip` is a plain archive; `overleaf_template` adds the template fixes, the report and a first compile (spec 120). */
export type ImportSourceKind = "zip" | "overleaf_template";

/** One line of the compatibility report of a template import (spec 120). */
export interface CompatFinding {
  ruleId: string;
  severity: "info" | "warning";
  path: string;
  line: number;
  message: string;
}

export interface ProjectImport {
  importId: string;
  projectId: string;
  status: ImportStatus;
  source: ImportSourceKind;
  compatReport: CompatFinding[] | null;
  reportSeenAt: string | null;
  entriesTotal: number | null;
  entriesImported: number | null;
  errorType: string | null;
  errorMessage: string | null;
}

type ProjectImportWire = Schemas["ProjectImportRead"];

function toFinding(wire: NonNullable<ProjectImportWire["compat_report"]>[number]): CompatFinding {
  return {
    ruleId: wire.rule_id,
    severity: wire.severity,
    path: wire.path,
    line: wire.line,
    message: wire.message,
  };
}

function toImport(wire: ProjectImportWire): ProjectImport {
  return {
    importId: wire.import_id,
    projectId: wire.project_id,
    status: wire.status,
    source: wire.source,
    compatReport: wire.compat_report?.map(toFinding) ?? null,
    reportSeenAt: wire.report_seen_at ?? null,
    entriesTotal: wire.entries_total ?? null,
    entriesImported: wire.entries_imported ?? null,
    errorType: wire.error_type ?? null,
    errorMessage: wire.error_message ?? null,
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
  source: ImportSourceKind = "zip",
): Promise<ProjectImport> {
  const form = new FormData();
  form.append("file", file);
  if (name && name.trim()) form.append("name", name.trim());
  form.append("source", source);

  return new Promise<ProjectImport>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${config.apiBaseUrl}/api/v1/projects/import`);
    const access = tokenStore.getAccessToken();
    if (access) xhr.setRequestHeader("Authorization", `Bearer ${access}`);

    xhr.upload.onprogress = (event) => {
      if (onProgress && event.lengthComputable) onProgress(event.loaded / event.total);
    };
    xhr.onerror = () => reject(new ImportUploadError(0, "upload_failed", "Network error during upload"));
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
  return toImport(await apiClient.get<ProjectImportWire>(`/api/v1/projects/${projectId}/import/${importId}`));
}

/** The project's latest import, or `null` for a project made from scratch (the route answers 404). */
export async function getLatestImport(projectId: string): Promise<ProjectImport | null> {
  try {
    return toImport(await apiClient.get<ProjectImportWire>(`/api/v1/projects/${projectId}/import`));
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) return null;
    throw err;
  }
}

/** Record that the person has seen the compatibility report; the server keeps the first stamp. */
export async function markImportReportSeen(projectId: string, importId: string): Promise<void> {
  await apiClient.post(`/api/v1/projects/${projectId}/import/${importId}/report-seen`);
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
