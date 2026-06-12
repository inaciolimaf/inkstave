/** Project API calls (spec 11). snake_case ↔ camelCase mapping lives here only. */
import { apiClient } from "@/lib/api-client";

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
