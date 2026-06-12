import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import i18n from "@/i18n/config";

import * as api from "./api";
import type { TreeNode } from "./types";
import { addChild, removeNode, reparent, updateNode } from "./tree-utils";

export function treeKey(projectId: string) {
  return ["project", projectId, "tree"] as const;
}

export function useProjectTree(projectId: string) {
  return useQuery({ queryKey: treeKey(projectId), queryFn: () => api.getTree(projectId) });
}

export function useCreateEntity(projectId: string) {
  const qc = useQueryClient();
  const key = treeKey(projectId);
  return useMutation({
    mutationFn: (input: { type: "folder" | "doc"; name: string; parentId: string | null }) =>
      api.createEntity(projectId, input),
    onMutate: async (input) => {
      await qc.cancelQueries({ queryKey: key });
      const previous = qc.getQueryData<TreeNode>(key);
      if (previous) {
        const parentId = input.parentId ?? previous.id;
        const temp: TreeNode = {
          id: `temp-${Math.random().toString(36).slice(2)}`,
          name: input.name,
          type: input.type,
          parentId,
          isRoot: false,
          path: "",
          children: [],
        };
        qc.setQueryData<TreeNode>(key, addChild(previous, parentId, temp));
      }
      return { previous };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.previous) qc.setQueryData(key, ctx.previous);
      toast.error(i18n.t("files:toast.createError"));
    },
    onSuccess: (entity) => toast.success(i18n.t("files:toast.created", { name: entity.name })),
    onSettled: () => qc.invalidateQueries({ queryKey: key }),
  });
}

export function useRenameEntity(projectId: string) {
  const qc = useQueryClient();
  const key = treeKey(projectId);
  return useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) =>
      api.renameEntity(projectId, id, name),
    onMutate: async ({ id, name }) => {
      await qc.cancelQueries({ queryKey: key });
      const previous = qc.getQueryData<TreeNode>(key);
      if (previous) qc.setQueryData<TreeNode>(key, updateNode(previous, id, { name }));
      return { previous };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.previous) qc.setQueryData(key, ctx.previous);
      toast.error(i18n.t("files:toast.renameError"));
    },
    onSuccess: () => toast.success(i18n.t("files:toast.renamed")),
    onSettled: () => qc.invalidateQueries({ queryKey: key }),
  });
}

export function useMoveEntity(projectId: string) {
  const qc = useQueryClient();
  const key = treeKey(projectId);
  return useMutation({
    mutationFn: ({ id, newParentId }: { id: string; newParentId: string }) =>
      api.moveEntity(projectId, id, newParentId),
    onMutate: async ({ id, newParentId }) => {
      await qc.cancelQueries({ queryKey: key });
      const previous = qc.getQueryData<TreeNode>(key);
      if (previous) qc.setQueryData<TreeNode>(key, reparent(previous, id, newParentId));
      return { previous };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.previous) qc.setQueryData(key, ctx.previous);
      toast.error(i18n.t("files:toast.moveError"));
    },
    onSuccess: () => toast.success(i18n.t("files:toast.moved")),
    onSettled: () => qc.invalidateQueries({ queryKey: key }),
  });
}

export function useDeleteEntity(projectId: string) {
  const qc = useQueryClient();
  const key = treeKey(projectId);
  return useMutation({
    mutationFn: (id: string) => api.deleteEntity(projectId, id),
    onMutate: async (id) => {
      await qc.cancelQueries({ queryKey: key });
      const previous = qc.getQueryData<TreeNode>(key);
      if (previous) qc.setQueryData<TreeNode>(key, removeNode(previous, id));
      return { previous };
    },
    onError: (_e, _id, ctx) => {
      if (ctx?.previous) qc.setQueryData(key, ctx.previous);
      toast.error(i18n.t("files:toast.deleteError"));
    },
    onSuccess: () => toast.success(i18n.t("files:toast.deleted")),
    onSettled: () => qc.invalidateQueries({ queryKey: key }),
  });
}
