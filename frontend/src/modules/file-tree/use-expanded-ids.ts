import { useCallback, useEffect, useState } from "react";

import { findNode } from "./tree-utils";
import type { TreeNode } from "./types";

/**
 * Tracks which folders are expanded, persisting the set per-project in
 * sessionStorage so the tree keeps its shape across navigations within a tab.
 */
export function useExpandedIds(projectId: string) {
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

/**
 * Where a new entity should be created/uploaded given the current selection:
 * the selected folder, the selected file's parent, or the tree root.
 */
export function resolveParentFolder(root: TreeNode, selectedId: string | null): string {
  if (!selectedId) return root.id;
  const sel = findNode(root, selectedId);
  if (!sel) return root.id;
  if (sel.type === "folder") return sel.id;
  return sel.parentId ?? root.id;
}
