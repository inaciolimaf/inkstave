import { useEffect, useRef } from "react";

import type { TreeEntity, TreeNode } from "@/modules/file-tree";

function docs(root: TreeNode): TreeNode[] {
  const queue = [root];
  const found: TreeNode[] = [];
  for (const node of queue) {
    if (node.type === "doc") found.push(node);
    queue.push(...node.children);
  }
  return found;
}

/** What a project opens on, so it never starts blank: its root document, `main.tex`, then the first `.tex`. */
export function pickStartDocument(root: TreeNode, rootDocId: string | null): TreeNode | null {
  const all = docs(root);
  return (
    all.find((d) => d.id === rootDocId) ??
    all.find((d) => d.name === "main.tex") ??
    all.find((d) => d.name.endsWith(".tex")) ??
    all[0] ??
    null
  );
}

/** Opens a document as soon as the project is known, so the screen never starts blank. */
export function useStartDocument(
  root: TreeNode | undefined,
  rootDocId: string | null | undefined,
  selected: TreeEntity | null,
  onSelect: (entity: TreeEntity) => void,
) {
  const started = useRef(false);
  useEffect(() => {
    if (started.current || selected) return;
    if (!root || rootDocId === undefined) return;
    started.current = true;
    const start = pickStartDocument(root, rootDocId);
    if (start) onSelect(start);
  }, [root, rootDocId, selected, onSelect]);
}
