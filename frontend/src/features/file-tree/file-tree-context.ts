import { createContext, useContext } from "react";

import type { TreeNode } from "./types";

export type MenuAction = "rename" | "delete" | "new-doc" | "new-folder" | "move-root" | "upload";

export interface FileTreeContextValue {
  selectedId: string | null;
  focusedId: string | null;
  expandedIds: Set<string>;
  renamingId: string | null;
  draggingId: string | null;
  dropTargetId: string | null;
  rootId: string;
  registerRow: (id: string, el: HTMLElement | null) => void;
  onToggle: (id: string) => void;
  onSelect: (node: TreeNode) => void;
  onActivate: (node: TreeNode) => void;
  onCommitRename: (id: string, name: string) => void;
  onCancelRename: () => void;
  onMenuAction: (action: MenuAction, node: TreeNode) => void;
  onDragStart: (id: string) => void;
  onDragEnterNode: (node: TreeNode) => void;
  onDropOnNode: (node: TreeNode) => void;
  onDragEnd: () => void;
}

export const FileTreeContext = createContext<FileTreeContextValue | null>(null);

export function useFileTreeContext(): FileTreeContextValue {
  const ctx = useContext(FileTreeContext);
  if (!ctx) throw new Error("useFileTreeContext must be used within a FileTreePanel");
  return ctx;
}
