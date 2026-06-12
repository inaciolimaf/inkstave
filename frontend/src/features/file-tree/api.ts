/** File-tree (spec 12) + binary upload (spec 14) API. Wire mapping lives here. */
import { apiClient } from "@/lib/api-client";
import { config } from "@/config";
import { tokenStore } from "@/lib/token-store";

import type { EntityType, TreeEntity, TreeNode } from "./types";

interface WireEntity {
  id: string;
  project_id: string;
  parent_id: string | null;
  type: EntityType;
  name: string;
  is_root: boolean;
  path: string;
}

interface WireNode extends WireEntity {
  children: WireNode[] | null;
}

function toEntity(w: WireEntity): TreeEntity {
  return {
    id: w.id,
    name: w.name,
    type: w.type,
    parentId: w.parent_id,
    isRoot: w.is_root,
    path: w.path,
  };
}

function toNode(w: WireNode): TreeNode {
  return { ...toEntity(w), children: (w.children ?? []).map(toNode) };
}

export async function getTree(projectId: string): Promise<TreeNode> {
  const data = await apiClient.get<{ root: WireNode }>(`/api/v1/projects/${projectId}/tree`);
  return toNode(data.root);
}

export async function createEntity(
  projectId: string,
  input: { type: "folder" | "doc"; name: string; parentId: string | null },
): Promise<TreeEntity> {
  const wire = await apiClient.post<WireEntity>(`/api/v1/projects/${projectId}/tree/entities`, {
    type: input.type,
    name: input.name,
    parent_id: input.parentId,
  });
  return toEntity(wire);
}

export async function renameEntity(
  projectId: string,
  id: string,
  name: string,
): Promise<TreeEntity> {
  const wire = await apiClient.patch<WireEntity>(
    `/api/v1/projects/${projectId}/tree/entities/${id}/rename`,
    { name },
  );
  return toEntity(wire);
}

export async function moveEntity(
  projectId: string,
  id: string,
  newParentId: string,
): Promise<TreeEntity> {
  const wire = await apiClient.patch<WireEntity>(
    `/api/v1/projects/${projectId}/tree/entities/${id}/move`,
    { new_parent_id: newParentId },
  );
  return toEntity(wire);
}

export async function deleteEntity(projectId: string, id: string): Promise<void> {
  await apiClient.delete(`/api/v1/projects/${projectId}/tree/entities/${id}`);
}

export class UploadError extends Error {
  constructor(
    public status: number,
    public code: string,
  ) {
    super(code);
    this.name = "UploadError";
  }
}

/** Upload a binary via multipart with byte-level progress (XHR; spec 14). */
export function uploadFile(
  projectId: string,
  input: { file: File; parentId: string | null; name?: string; onProgress?: (pct: number) => void },
): Promise<TreeEntity> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${config.apiBaseUrl}/api/v1/projects/${projectId}/files`);
    const token = tokenStore.getAccessToken();
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && input.onProgress) {
        input.onProgress(Math.round((e.loaded / e.total) * 100));
      }
    };
    xhr.onload = () => {
      if (xhr.status === 201) {
        try {
          resolve(toEntity(JSON.parse(xhr.responseText) as WireEntity));
        } catch {
          reject(new UploadError(xhr.status, "invalid_response"));
        }
        return;
      }
      let code = "upload_failed";
      try {
        code = (JSON.parse(xhr.responseText) as { error?: { type?: string } }).error?.type ?? code;
      } catch {
        /* keep default */
      }
      reject(new UploadError(xhr.status, code));
    };
    xhr.onerror = () => reject(new UploadError(0, "network_error"));

    const form = new FormData();
    form.append("file", input.file);
    if (input.parentId) form.append("parent_id", input.parentId);
    if (input.name) form.append("name", input.name);
    xhr.send(form);
  });
}
