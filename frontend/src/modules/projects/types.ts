/** Camel-cased project shape used throughout the UI (mapped at the API boundary). */
export interface Project {
  id: string;
  name: string;
  ownerId: string;
  rootDocId: string | null;
  createdAt: string;
  updatedAt: string;
}

/** The caller's role in a project, as the membership table names it (spec 109). */
export type ProjectRole = "owner" | "editor" | "viewer";

/** The dashboard filter: every project, the caller's own, or the ones shared with them. */
export type ProjectScope = "all" | "owned" | "shared";

export interface ProjectOwner {
  id: string;
  displayName: string;
}

/** A project in the caller's dashboard list: the caller's role and who owns it (spec 109). */
export interface ListedProject extends Project {
  role: ProjectRole;
  owner: ProjectOwner;
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
