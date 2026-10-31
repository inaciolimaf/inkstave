import { useCallback, useState } from "react";
import { toast } from "sonner";

import i18n from "@/i18n/config";

import type { MenuAction } from "./file-tree-context";
import { findNode, isSelfOrDescendant } from "./tree-utils";
import type { TreeNode } from "./types";
import { useCreateEntity, useDeleteEntity, useMoveEntity, useRenameEntity } from "./use-file-tree";

type DialogState =
  | { kind: "create"; createType: "folder" | "doc"; parentId: string }
  | { kind: "delete"; node: TreeNode }
  | null;

interface TreeActionsArgs {
  projectId: string;
  root: TreeNode | null;
  readOnly: boolean;
  selectedId: string | null;
  setSelectedId: (id: string | null) => void;
  expand: (id: string) => void;
  startRename: (id: string) => void;
  triggerUpload: (parentId: string) => void;
}

/** Every change to the tree, with the dialogs that confirm them. Viewers get none (spec 34 §5.3). */
export function useTreeActions({
  projectId,
  root,
  readOnly,
  selectedId,
  setSelectedId,
  expand,
  startRename,
  triggerUpload,
}: TreeActionsArgs) {
  const createMut = useCreateEntity(projectId);
  const renameMut = useRenameEntity(projectId);
  const moveMut = useMoveEntity(projectId);
  const deleteMut = useDeleteEntity(projectId);
  const [dialog, setDialog] = useState<DialogState>(null);

  const openCreate = useCallback(
    (createType: "folder" | "doc", parentId: string) => {
      expand(parentId);
      setDialog({ kind: "create", createType, parentId });
    },
    [expand],
  );

  const move = useCallback(
    (id: string, newParentId: string) => {
      if (readOnly) return; // no move/drag for viewers (spec 34 §5.3)
      if (!root || id === newParentId) return;
      if (isSelfOrDescendant(root, id, newParentId)) {
        toast.error(i18n.t("files:toast.moveIntoSelf"));
        return;
      }
      const dragged = findNode(root, id);
      if (dragged && dragged.parentId === newParentId) return; // already there
      expand(newParentId);
      moveMut.mutate({ id, newParentId });
    },
    [readOnly, root, moveMut, expand],
  );

  const requestDelete = useCallback((node: TreeNode) => setDialog({ kind: "delete", node }), []);

  const onMenuAction = useCallback(
    (action: MenuAction, node: TreeNode) => {
      if (readOnly) return; // viewers get no mutation actions (spec 34 §5.3)
      switch (action) {
        case "rename":
          startRename(node.id);
          break;
        case "delete":
          requestDelete(node);
          break;
        case "new-doc":
          openCreate("doc", node.id);
          break;
        case "new-folder":
          openCreate("folder", node.id);
          break;
        case "move-root":
          if (root) move(node.id, root.id);
          break;
        case "upload":
          triggerUpload(node.id);
          break;
      }
    },
    [readOnly, startRename, requestDelete, openCreate, move, root, triggerUpload],
  );

  const commitRename = (id: string, name: string) => {
    if (readOnly || !root) return;
    const node = findNode(root, id);
    if (node && node.name !== name) renameMut.mutate({ id, name });
  };

  const confirmCreate = useCallback(
    (name: string) => {
      if (dialog?.kind !== "create") return;
      createMut.mutate({ type: dialog.createType, name, parentId: dialog.parentId });
      setDialog(null);
    },
    [dialog, createMut],
  );

  const confirmDelete = useCallback(() => {
    if (dialog?.kind !== "delete") return;
    const { node } = dialog;
    deleteMut.mutate(node.id);
    if (selectedId === node.id) setSelectedId(null);
    setDialog(null);
  }, [dialog, deleteMut, selectedId, setSelectedId]);

  return {
    dialog,
    closeDialog: () => setDialog(null),
    openCreate,
    move,
    requestDelete,
    onMenuAction,
    commitRename,
    confirmCreate,
    confirmDelete,
  };
}
