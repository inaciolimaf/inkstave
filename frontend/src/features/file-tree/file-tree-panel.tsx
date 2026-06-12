import { useQueryClient } from "@tanstack/react-query";
import { FilePlus, FolderPlus, Upload, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

import { UploadError, uploadFile } from "./api";
import { FileTreeContext, type FileTreeContextValue, type MenuAction } from "./file-tree-context";
import { CreateEntityDialog, DeleteEntityDialog } from "./file-tree-dialogs";
import { FileTreeNode } from "./file-tree-node";
import { findNode, flattenVisible, isSelfOrDescendant, sortNodes } from "./tree-utils";
import type { TreeEntity, TreeNode } from "./types";
import {
  treeKey,
  useCreateEntity,
  useDeleteEntity,
  useMoveEntity,
  useProjectTree,
  useRenameEntity,
} from "./use-file-tree";

function useExpandedIds(projectId: string) {
  const storageKey = `inkstave:tree-expanded:${projectId}`;
  const [expanded, setExpanded] = useState<Set<string>>(() => {
    try {
      const raw = sessionStorage.getItem(storageKey);
      return new Set(raw ? (JSON.parse(raw) as string[]) : []);
    } catch {
      return new Set();
    }
  });
  useEffect(() => {
    try {
      sessionStorage.setItem(storageKey, JSON.stringify([...expanded]));
    } catch {
      /* ignore */
    }
  }, [expanded, storageKey]);
  const toggle = useCallback((id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);
  const expand = useCallback((id: string) => {
    setExpanded((prev) => new Set(prev).add(id));
  }, []);
  const collapse = useCallback((id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
  }, []);
  return { expanded, toggle, expand, collapse };
}

function resolveParentFolder(root: TreeNode, selectedId: string | null): string {
  if (!selectedId) return root.id;
  const sel = findNode(root, selectedId);
  if (!sel) return root.id;
  if (sel.type === "folder") return sel.id;
  return sel.parentId ?? root.id;
}

interface UploadItem {
  key: string;
  name: string;
  pct: number;
  status: "uploading" | "done" | "error";
  error?: string;
}

type DialogState =
  | { kind: "create"; createType: "folder" | "doc"; parentId: string }
  | { kind: "delete"; node: TreeNode }
  | null;

export function FileTreePanel({
  projectId,
  selectedId: selectedIdProp,
  onSelectEntity,
}: {
  projectId: string;
  selectedId: string | null;
  onSelectEntity: (entity: TreeEntity) => void;
}) {
  const treeQuery = useProjectTree(projectId);
  const root = treeQuery.data ?? null;
  const qc = useQueryClient();

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
  const [uploads, setUploads] = useState<UploadItem[]>([]);

  const rowRefs = useRef(new Map<string, HTMLElement>());
  const uploadInputRef = useRef<HTMLInputElement>(null);
  const uploadParentRef = useRef<string | null>(null);

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

  const triggerUpload = useCallback((parentId: string) => {
    uploadParentRef.current = parentId;
    uploadInputRef.current?.click();
  }, []);

  const openCreate = useCallback(
    (createType: "folder" | "doc", parentId: string) => {
      expand(parentId);
      setDialog({ kind: "create", createType, parentId });
    },
    [expand],
  );

  const doMove = useCallback(
    (id: string, newParentId: string) => {
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
    [root, moveMut, expand],
  );

  const onMenuAction = useCallback(
    (action: MenuAction, node: TreeNode) => {
      switch (action) {
        case "rename":
          startRename(node.id);
          break;
        case "delete":
          setDialog({ kind: "delete", node });
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
          triggerUpload(node.id);
          break;
      }
    },
    [startRename, openCreate, doMove, root, triggerUpload],
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

  const onFilesPicked = useCallback(
    async (files: FileList) => {
      const parentId = uploadParentRef.current;
      for (const file of Array.from(files)) {
        const key = `${file.name}-${Math.random().toString(36).slice(2)}`;
        setUploads((u) => [...u, { key, name: file.name, pct: 0, status: "uploading" }]);
        try {
          await uploadFile(projectId, {
            file,
            parentId,
            onProgress: (pct) =>
              setUploads((u) => u.map((it) => (it.key === key ? { ...it, pct } : it))),
          });
          setUploads((u) =>
            u.map((it) => (it.key === key ? { ...it, pct: 100, status: "done" } : it)),
          );
          toast.success(`Uploaded ${file.name}`);
          await qc.invalidateQueries({ queryKey: treeKey(projectId) });
        } catch (err) {
          const code = err instanceof UploadError ? err.code : "upload_failed";
          setUploads((u) =>
            u.map((it) => (it.key === key ? { ...it, status: "error", error: code } : it)),
          );
          toast.error(
            code === "name_conflict"
              ? `“${file.name}” already exists`
              : `Upload of ${file.name} failed`,
          );
        }
      }
      if (uploadInputRef.current) uploadInputRef.current.value = "";
    },
    [projectId, qc],
  );

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (renamingId) return;
    const idx = flat.findIndex((f) => f.node.id === focusedId);
    if (idx < 0) return;
    const current = flat[idx];
    const key = e.key;

    if (key === "ArrowDown") {
      e.preventDefault();
      focusRow(flat[Math.min(idx + 1, flat.length - 1)].node.id);
    } else if (key === "ArrowUp") {
      e.preventDefault();
      focusRow(flat[Math.max(idx - 1, 0)].node.id);
    } else if (key === "ArrowRight") {
      e.preventDefault();
      if (current.node.type === "folder") {
        if (!expanded.has(current.node.id)) expand(current.node.id);
        else if (flat[idx + 1]) focusRow(flat[idx + 1].node.id);
      }
    } else if (key === "ArrowLeft") {
      e.preventDefault();
      if (current.node.type === "folder" && expanded.has(current.node.id)) {
        collapse(current.node.id);
      } else if (current.parentId && root && current.parentId !== root.id) {
        focusRow(current.parentId);
      }
    } else if (key === "Enter") {
      e.preventDefault();
      activate(current.node);
    } else if (key === "F2") {
      e.preventDefault();
      startRename(current.node.id);
    } else if (key === "Delete") {
      e.preventDefault();
      setDialog({ kind: "delete", node: current.node });
    } else if (key === "Home") {
      e.preventDefault();
      focusRow(flat[0].node.id);
    } else if (key === "End") {
      e.preventDefault();
      focusRow(flat[flat.length - 1].node.id);
    } else if (key.length === 1 && /\S/.test(key) && !e.ctrlKey && !e.metaKey && !e.altKey) {
      const lower = key.toLowerCase();
      for (let i = 1; i <= flat.length; i++) {
        const f = flat[(idx + i) % flat.length];
        if (f.node.name.toLowerCase().startsWith(lower)) {
          focusRow(f.node.id);
          break;
        }
      }
    }
  };

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
          const node = findNode(root, id);
          if (node && node.name !== name) renameMut.mutate({ id, name });
        },
        onCancelRename: () => setRenamingId(null),
        onMenuAction,
        onDragStart: (id) => setDraggingId(id),
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
      <TooltipProvider delayDuration={300}>
        <div className="flex items-center gap-1 border-b px-2 py-1">
          <span className="mr-auto text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Files
          </span>
          {[
            {
              icon: FilePlus,
              label: "New file",
              run: () => root && openCreate("doc", resolveParentFolder(root, selectedId)),
            },
            {
              icon: FolderPlus,
              label: "New folder",
              run: () => root && openCreate("folder", resolveParentFolder(root, selectedId)),
            },
            {
              icon: Upload,
              label: "Upload file",
              run: () => root && triggerUpload(resolveParentFolder(root, selectedId)),
            },
          ].map(({ icon: Icon, label, run }) => (
            <Tooltip key={label}>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={label}
                  disabled={!root}
                  onClick={run}
                >
                  <Icon className="size-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>{label}</TooltipContent>
            </Tooltip>
          ))}
        </div>
      </TooltipProvider>

      <input
        ref={uploadInputRef}
        type="file"
        multiple
        className="hidden"
        aria-hidden
        onChange={(e) => e.target.files && onFilesPicked(e.target.files)}
      />

      <div className="flex-1 overflow-auto p-1">
        {treeQuery.isLoading && (
          <div className="space-y-2 p-1" aria-busy="true" aria-label="Loading files">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-6 w-full" />
            ))}
          </div>
        )}

        {treeQuery.isError && (
          <div role="alert" className="space-y-2 p-3 text-center text-sm">
            <p className="text-destructive">Couldn’t load the file tree.</p>
            <Button variant="outline" size="sm" onClick={() => void treeQuery.refetch()}>
              Retry
            </Button>
          </div>
        )}

        {ctx && root && (
          <FileTreeContext.Provider value={ctx}>
            {root.children.length === 0 ? (
              <div className="space-y-2 p-3 text-center text-sm text-muted-foreground">
                <p>No files yet — create one.</p>
                <div className="flex justify-center gap-2">
                  <Button size="sm" variant="outline" onClick={() => openCreate("doc", root.id)}>
                    New file
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => triggerUpload(root.id)}>
                    Upload
                  </Button>
                </div>
              </div>
            ) : (
              <ul
                role="tree"
                aria-label="Project files"
                className="select-none"
                onKeyDown={onKeyDown}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDropTargetId(root.id);
                }}
                onDrop={(e) => {
                  e.preventDefault();
                  setDropTargetId(null);
                  if (draggingId) doMove(draggingId, root.id);
                  setDraggingId(null);
                }}
              >
                {sortNodes(root.children).map((child) => (
                  <FileTreeNode key={child.id} node={child} depth={0} />
                ))}
              </ul>
            )}
          </FileTreeContext.Provider>
        )}
      </div>

      {uploads.length > 0 && (
        <ul className="space-y-1 border-t p-2" aria-label="Uploads">
          {uploads.map((u) => (
            <li key={u.key} className="space-y-1 text-xs">
              <div className="flex items-center justify-between gap-2">
                <span className="truncate">{u.name}</span>
                <div className="flex items-center gap-1">
                  <span
                    className={u.status === "error" ? "text-destructive" : "text-muted-foreground"}
                  >
                    {u.status === "error" ? "Failed" : u.status === "done" ? "Done" : `${u.pct}%`}
                  </span>
                  {u.status !== "uploading" && (
                    <button
                      type="button"
                      aria-label={`Dismiss ${u.name}`}
                      onClick={() => setUploads((list) => list.filter((it) => it.key !== u.key))}
                    >
                      <X className="size-3" />
                    </button>
                  )}
                </div>
              </div>
              {u.status === "uploading" && <Progress value={u.pct} />}
            </li>
          ))}
        </ul>
      )}

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
    </div>
  );
}
