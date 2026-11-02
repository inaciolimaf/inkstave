import { useEffect, useRef } from "react";

import type { TreeEntity, TreeNode } from "@/modules/file-tree";

function index(root: TreeNode): Map<string, TreeNode> {
  const nodes = new Map<string, TreeNode>();
  const queue = [root];
  for (const node of queue) {
    nodes.set(node.id, node);
    queue.push(...node.children);
  }
  return nodes;
}

/**
 * What the selection should become after the tree changed: `undefined` to leave it, `null` when
 * it was removed, or the same entity at its new path. An id the tree has not listed yet (a file
 * just created, before the refetch) is left alone: only what *was* there can have gone.
 */
export function selectionAfterTreeChange(
  known: ReadonlySet<string>,
  nodes: ReadonlyMap<string, TreeNode>,
  selected: TreeEntity,
): TreeNode | null | undefined {
  const node = nodes.get(selected.id);
  if (!node) return known.has(selected.id) ? null : undefined;
  return node.path === selected.path ? undefined : node;
}

/** Keeps the open file right when something other than the file drawer changes the tree. */
export function useSelectionFollowsTree(
  root: TreeNode | undefined,
  selected: TreeEntity | null,
  onSelect: (entity: TreeEntity | null) => void,
) {
  const known = useRef<ReadonlySet<string>>(new Set());
  useEffect(() => {
    if (!root) return;
    const nodes = index(root);
    const next = selected ? selectionAfterTreeChange(known.current, nodes, selected) : undefined;
    known.current = new Set(nodes.keys());
    if (next !== undefined) onSelect(next);
  }, [root, selected, onSelect]);
}
