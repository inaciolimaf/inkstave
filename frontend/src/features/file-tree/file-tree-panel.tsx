import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { FileTreeBody } from "./file-tree-body";
import { type FileTreeContextValue, type MenuAction } from "./file-tree-context";
import { CreateEntityDialog, DeleteEntityDialog } from "./file-tree-dialogs";
import { FileTreeToolbar } from "./file-tree-toolbar";
import { UploadConflictDialog, UploadList } from "./file-tree-uploads-ui";
import { findNode, flattenVisible, isSelfOrDescendant } from "./tree-utils";
import type { TreeEntity, TreeNode } from "./types";
import { resolveParentFolder, useExpandedIds } from "./use-expanded-ids";
import {
  useCreateEntity,
  useDeleteEntity,
  useMoveEntity,
  useProjectTree,
  useRenameEntity,
} from "./use-file-tree";
import { useTreeKeyboard } from "./use-tree-keyboard";
import { useUploads } from "./use-uploads";

type DialogState =
  | { kind: "create"; createType: "folder" | "doc"; parentId: string }
  | { kind: "delete"; node: TreeNode }
  | null;

export function FileTreePanel({
  projectId,
  selectedId: selectedIdProp,
  onSelectEntity,
  readOnly = false,
}: {
  projectId: string;
  selectedId: string | null;
  onSelectEntity: (entity: TreeEntity) => void;
  /** Viewers / read-only collaborators see no file-tree mutation actions (spec 34 §5.3). */
  readOnly?: boolean;
}) {
  const treeQuery = useProjectTree(projectId);
  const root = treeQuery.data ?? null;

  const createMut = useCreateEntity(projectId);
  const renameMut = useRenameEntity(projectId);
  const moveMut = useMoveEntity(projectId);
  const deleteMut = useDeleteEntity(projectId);

  const { expanded, toggle, expand, collapse } = useExpandedIds(projectId);
  const [selectedId, setSelectedId] = useState<string | null>(selectedIdProp);
  useEffect(() => setSelectedId(selectedIdProp), [selectedIdProp]);
  const [focusedId, setFocusedId] = useState<string | null>(null);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [dialog, setDialog] = useState<DialogState>(null);
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [dropTargetId, setDropTargetId] = useState<string | null>(null);

  const uploads = useUploads(projectId);

  const rowRefs = useRef(new Map<string, HTMLElement>());

  const flat = useMemo(() => (root ? flattenVisible(root, expanded) : []), [root, expanded]);

  // Seed roving focus on the first visible node once the tree loads.
  useEffect(() => {
    if (!focusedId && flat.length > 0) setFocusedId(flat[0].node.id);
  }, [flat, focusedId]);

  const focusRow = useCallback((id: string) => {
    setFocusedId(id);
    rowRefs.current.get(id)?.focus();
  }, []);

  const registerRow = useCallback((id: string, el: HTMLElement | null) => {
    if (el) rowRefs.current.set(id, el);
    else rowRefs.current.delete(id);
  }, []);

  const startRename = useCallback((id: string) => {
    // Defer so an open menu finishes closing (releasing focus) before the
    // inline input mounts and autofocuses — otherwise the close blurs it.
    setTimeout(() => setRenamingId(id), 0);
  }, []);

  const select = useCallback(
    (node: TreeNode) => {
      setSelectedId(node.id);
      if (node.type !== "folder") {
        onSelectEntity({
          id: node.id,
          name: node.name,
          type: node.type,
          parentId: node.parentId,
          isRoot: node.isRoot,
          path: node.path,
        });
      }
    },
    [onSelectEntity],
  );

  const activate = useCallback(
    (node: TreeNode) => {
      if (node.type === "folder") toggle(node.id);
      else select(node);
    },
    [toggle, select],
  );

  const openCreate = useCallback(
    (createType: "folder" | "doc", parentId: string) => {
      expand(parentId);
      setDialog({ kind: "create", createType, parentId });
    },
    [expand],
  );

  const doMove = useCallback(
    (id: string, newParentId: string) => {
      if (readOnly) return; // no move/drag for viewers (spec 34 §5.3)
      if (!root || id === newParentId) return;
      if (isSelfOrDescendant(root, id, newParentId)) {
        toast.error("Can’t move a folder into itself");
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
          if (root) doMove(node.id, root.id);
          break;
        case "upload":
          uploads.triggerUpload(node.id);
          break;
      }
    },
    [readOnly, startRename, requestDelete, openCreate, doMove, root, uploads],
  );

  const onCreateConfirm = useCallback(
    (name: string) => {
      if (dialog?.kind !== "create") return;
      createMut.mutate({ type: dialog.createType, name, parentId: dialog.parentId });
      setDialog(null);
    },
    [dialog, createMut],
  );

  const onDeleteConfirm = useCallback(() => {
    if (dialog?.kind !== "delete") return;
    const { node } = dialog;
    deleteMut.mutate(node.id);
    if (selectedId === node.id) setSelectedId(null);
    setDialog(null);
  }, [dialog, deleteMut, selectedId]);

  const onKeyDown = useTreeKeyboard({
    flat,
    focusedId,
    renamingId,
    readOnly,
    rootId: root?.id ?? null,
    expanded,
    focusRow,
    expand,
    collapse,
    activate,
    startRename,
    requestDelete,
  });

  const ctx: FileTreeContextValue | null = root
    ? {
        selectedId,
        focusedId,
        expandedIds: expanded,
        renamingId,
        draggingId,
        dropTargetId,
        rootId: root.id,
        registerRow,
        onToggle: toggle,
        onSelect: select,
        onActivate: activate,
        onCommitRename: (id, name) => {
          setRenamingId(null);
          if (readOnly) return;
          const node = findNode(root, id);
          if (node && node.name !== name) renameMut.mutate({ id, name });
        },
        onCancelRename: () => setRenamingId(null),
        onMenuAction,
        onDragStart: (id) => !readOnly && setDraggingId(id),
        onDragEnterNode: (node) => setDropTargetId(node.id),
        onDropOnNode: (node) => {
          setDropTargetId(null);
          if (draggingId) doMove(draggingId, node.id);
          setDraggingId(null);
        },
        onDragEnd: () => {
          setDraggingId(null);
          setDropTargetId(null);
        },
      }
    : null;

  return (
    <div className="flex h-full flex-col">
      <FileTreeToolbar
        readOnly={readOnly}
        hasRoot={!!root}
        onNewDoc={() => root && openCreate("doc", resolveParentFolder(root, selectedId))}
        onNewFolder={() => root && openCreate("folder", resolveParentFolder(root, selectedId))}
        onUpload={() => root && uploads.triggerUpload(resolveParentFolder(root, selectedId))}
      />

      <input
        ref={uploads.uploadInputRef}
        type="file"
        multiple
        className="hidden"
        aria-hidden
        onChange={(e) => e.target.files && uploads.onFilesPicked(e.target.files)}
      />

      <FileTreeBody
        isLoading={treeQuery.isLoading}
        isError={treeQuery.isError}
        onRetry={() => void treeQuery.refetch()}
        ctx={ctx}
        root={root}
        readOnly={readOnly}
        onKeyDown={onKeyDown}
        onRootDragOver={(e) => {
          e.preventDefault();
          if (root) setDropTargetId(root.id);
        }}
        onRootDrop={(e) => {
          e.preventDefault();
          setDropTargetId(null);
          if (root && draggingId) doMove(draggingId, root.id);
          setDraggingId(null);
        }}
        onNewDoc={() => root && openCreate("doc", root.id)}
        onUpload={() => root && uploads.triggerUpload(root.id)}
      />

      <UploadList uploads={uploads.uploads} onDismiss={uploads.dismissUpload} />

      <CreateEntityDialog
        open={dialog?.kind === "create"}
        type={dialog?.kind === "create" ? dialog.createType : "doc"}
        onOpenChange={(v) => !v && setDialog(null)}
        onCreate={onCreateConfirm}
      />
      <DeleteEntityDialog
        open={dialog?.kind === "delete"}
        node={dialog?.kind === "delete" ? dialog.node : null}
        onOpenChange={(v) => !v && setDialog(null)}
        onConfirm={onDeleteConfirm}
      />
      <UploadConflictDialog
        conflict={uploads.conflict}
        onCancel={() => uploads.setConflict(null)}
        onReplace={() => void uploads.onReplaceConflict()}
      />
    </div>
  );
}
