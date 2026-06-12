/** Camel-cased project shape used throughout the UI (mapped at the API boundary). */
export interface Project {
  id: string;
  name: string;
  ownerId: string;
  createdAt: string;
  updatedAt: string;
}

export type SortKey = "updatedAt" | "name" | "createdAt";

/** Wire shape returned by the project-list endpoint (spec 16 §5.1). */
export interface ProjectListResponse {
  projects: Project[];
}

/** Request body for creating a project (spec 16 §5.1). */
export interface CreateProjectRequest {
  name: string;
}
