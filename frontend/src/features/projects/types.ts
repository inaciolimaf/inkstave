/** Camel-cased project shape used throughout the UI (mapped at the API boundary). */
export interface Project {
  id: string;
  name: string;
  ownerId: string;
  createdAt: string;
  updatedAt: string;
}

export type SortKey = "updatedAt" | "name" | "createdAt";
