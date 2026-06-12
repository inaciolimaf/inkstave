import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import * as api from "./api";
import type { Project, SortKey } from "./types";

export const PROJECTS_KEY = ["projects"] as const;

export function useProjects() {
  return useQuery({ queryKey: PROJECTS_KEY, queryFn: api.listProjects });
}

export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => api.createProject(name),
    onSuccess: (project) => {
      qc.setQueryData<Project[]>(PROJECTS_KEY, (old) => [project, ...(old ?? [])]);
      toast.success("Project created");
    },
    onError: () => toast.error("Could not create project"),
  });
}

export function useRenameProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) => api.renameProject(id, name),
    onMutate: async ({ id, name }) => {
      await qc.cancelQueries({ queryKey: PROJECTS_KEY });
      const previous = qc.getQueryData<Project[]>(PROJECTS_KEY);
      qc.setQueryData<Project[]>(PROJECTS_KEY, (old) =>
        old?.map((p) => (p.id === id ? { ...p, name } : p)),
      );
      return { previous };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.previous) qc.setQueryData(PROJECTS_KEY, ctx.previous);
      toast.error("Could not rename project");
    },
    onSuccess: () => toast.success("Project renamed"),
    onSettled: () => qc.invalidateQueries({ queryKey: PROJECTS_KEY }),
  });
}

export function useDeleteProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteProject(id),
    onMutate: async (id) => {
      await qc.cancelQueries({ queryKey: PROJECTS_KEY });
      const previous = qc.getQueryData<Project[]>(PROJECTS_KEY);
      qc.setQueryData<Project[]>(PROJECTS_KEY, (old) => old?.filter((p) => p.id !== id));
      return { previous };
    },
    onError: (_err, _id, ctx) => {
      if (ctx?.previous) qc.setQueryData(PROJECTS_KEY, ctx.previous);
      toast.error("Could not delete project");
    },
    onSuccess: () => toast.success("Project deleted"),
    onSettled: () => qc.invalidateQueries({ queryKey: PROJECTS_KEY }),
  });
}

/** Pure derivation: filter by name (case-insensitive) then sort. */
export function visibleProjects(projects: Project[], search: string, sortKey: SortKey): Project[] {
  const term = search.trim().toLowerCase();
  const filtered = term ? projects.filter((p) => p.name.toLowerCase().includes(term)) : projects;
  const sorted = [...filtered];
  sorted.sort((a, b) => {
    if (sortKey === "name") return a.name.localeCompare(b.name);
    if (sortKey === "createdAt") return b.createdAt.localeCompare(a.createdAt);
    return b.updatedAt.localeCompare(a.updatedAt);
  });
  return sorted;
}
