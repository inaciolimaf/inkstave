import { useCallback } from "react";

import type { FlatNode, TreeNode } from "./types";

interface KeyboardArgs {
  flat: FlatNode[];
  focusedId: string | null;
  renamingId: string | null;
  readOnly: boolean;
  rootId: string | null;
  expanded: Set<string>;
  focusRow: (id: string) => void;
  expand: (id: string) => void;
  collapse: (id: string) => void;
  activate: (node: TreeNode) => void;
  startRename: (id: string) => void;
  requestDelete: (node: TreeNode) => void;
}

/**
 * The full tree keyboard model (spec 17 §8): arrow navigation, expand/collapse,
 * activate, rename (F2), delete, Home/End, and type-ahead. Returns the `onKeyDown`
 * handler bound to the `role="tree"` container.
 */
export function useTreeKeyboard({
  flat,
  focusedId,
  renamingId,
  readOnly,
  rootId,
  expanded,
  focusRow,
  expand,
  collapse,
  activate,
  startRename,
  requestDelete,
}: KeyboardArgs) {
  return useCallback(
    (e: React.KeyboardEvent) => {
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
        } else if (current.parentId && rootId && current.parentId !== rootId) {
          focusRow(current.parentId);
        }
      } else if (key === "Enter") {
        e.preventDefault();
        activate(current.node);
      } else if (key === "F2") {
        e.preventDefault();
        if (!readOnly) startRename(current.node.id);
      } else if (key === "Delete") {
        e.preventDefault();
        if (!readOnly) requestDelete(current.node);
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
    },
    [
      flat,
      focusedId,
      renamingId,
      readOnly,
      rootId,
      expanded,
      focusRow,
      expand,
      collapse,
      activate,
      startRename,
      requestDelete,
    ],
  );
}
