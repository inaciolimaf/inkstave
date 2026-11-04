import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import i18n from "@/i18n/config";
import * as api from "./api";
import type { ListedProject, ProjectScope, SortKey } from "./types";

export const PROJECTS_KEY = ["projects"] as const;

export function useProjects() {
  return useQuery({ queryKey: PROJECTS_KEY, queryFn: api.listProjects });
}

export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => api.createProject(name),
    // The create answer has no role or owner name, so the list is refetched instead of patched.
    onSuccess: () => {
      toast.success(i18n.t("projects:toast.created"));
      void qc.invalidateQueries({ queryKey: PROJECTS_KEY });
    },
    onError: () => toast.error(i18n.t("projects:toast.createError")),
  });
}

export function useRenameProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) => api.renameProject(id, name),
    onMutate: async ({ id, name }) => {
      await qc.cancelQueries({ queryKey: PROJECTS_KEY });
      const previous = qc.getQueryData<ListedProject[]>(PROJECTS_KEY);
      qc.setQueryData<ListedProject[]>(PROJECTS_KEY, (old) =>
        old?.map((p) => (p.id === id ? { ...p, name } : p)),
      );
      return { previous };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.previous) qc.setQueryData(PROJECTS_KEY, ctx.previous);
      toast.error(i18n.t("projects:toast.renameError"));
    },
    onSuccess: () => toast.success(i18n.t("projects:toast.renamed")),
    onSettled: () => qc.invalidateQueries({ queryKey: PROJECTS_KEY }),
  });
}

export function useDeleteProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteProject(id),
    onMutate: async (id) => {
      await qc.cancelQueries({ queryKey: PROJECTS_KEY });
      const previous = qc.getQueryData<ListedProject[]>(PROJECTS_KEY);
      qc.setQueryData<ListedProject[]>(PROJECTS_KEY, (old) => old?.filter((p) => p.id !== id));
      return { previous };
    },
    onError: (_err, _id, ctx) => {
      if (ctx?.previous) qc.setQueryData(PROJECTS_KEY, ctx.previous);
      toast.error(i18n.t("projects:toast.deleteError"));
    },
    onSuccess: () => toast.success(i18n.t("projects:toast.deleted")),
    onSettled: () => qc.invalidateQueries({ queryKey: PROJECTS_KEY }),
  });
}

export function useLeaveProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, userId }: { id: string; userId: string }) => api.leaveProject(id, userId),
    onMutate: async ({ id }) => {
      await qc.cancelQueries({ queryKey: PROJECTS_KEY });
      const previous = qc.getQueryData<ListedProject[]>(PROJECTS_KEY);
      qc.setQueryData<ListedProject[]>(PROJECTS_KEY, (old) => old?.filter((p) => p.id !== id));
      return { previous };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.previous) qc.setQueryData(PROJECTS_KEY, ctx.previous);
      toast.error(i18n.t("projects:toast.leaveError"));
    },
    onSuccess: () => toast.success(i18n.t("projects:toast.left")),
    onSettled: () => qc.invalidateQueries({ queryKey: PROJECTS_KEY }),
  });
}

const SCOPES: readonly ProjectScope[] = ["all", "owned", "shared"];

/** Reads `?scope=` from the URL; anything unknown means "all". */
export function parseScope(value: string | null): ProjectScope {
  return SCOPES.find((scope) => scope === value) ?? "all";
}

function inScope(project: ListedProject, scope: ProjectScope): boolean {
  if (scope === "owned") return project.role === "owner";
  if (scope === "shared") return project.role !== "owner";
  return true;
}

/** Pure derivation: filter by scope and name (case-insensitive), then sort. */
export function visibleProjects(
  projects: ListedProject[],
  search: string,
  sortKey: SortKey,
  scope: ProjectScope = "all",
): ListedProject[] {
  const term = search.trim().toLowerCase();
  const filtered = projects.filter(
    (p) => inScope(p, scope) && (!term || p.name.toLowerCase().includes(term)),
  );
  const sorted = [...filtered];
  sorted.sort((a, b) => {
    if (sortKey === "name") return a.name.localeCompare(b.name);
    if (sortKey === "createdAt") return b.createdAt.localeCompare(a.createdAt);
    return b.updatedAt.localeCompare(a.updatedAt);
  });
  return sorted;
}
