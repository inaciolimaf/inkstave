import type { FlatNode, TreeNode } from "./types";

/** Folders first, then alphabetical (case-insensitive) by name. */
export function sortNodes(nodes: TreeNode[]): TreeNode[] {
  return [...nodes].sort((a, b) => {
    if (a.type === "folder" && b.type !== "folder") return -1;
    if (a.type !== "folder" && b.type === "folder") return 1;
    return a.name.localeCompare(b.name, undefined, { sensitivity: "base" });
  });
}

/** Recursively sort a node's children (folders first, alphabetical). */
export function sortTree(node: TreeNode): TreeNode {
  return { ...node, children: sortNodes(node.children).map(sortTree) };
}

/**
 * Flatten the visible nodes (children of the root whose ancestor folders are
 * all expanded) into the order they appear on screen — the basis for arrow-key
 * navigation and roving tabindex.
 */
export function flattenVisible(root: TreeNode, expanded: Set<string>): FlatNode[] {
  const out: FlatNode[] = [];
  const walk = (nodes: TreeNode[], depth: number, parentId: string | null) => {
    for (const node of sortNodes(nodes)) {
      out.push({ node, depth, parentId });
      if (node.type === "folder" && expanded.has(node.id)) {
        walk(node.children, depth + 1, node.id);
      }
    }
  };
  walk(root.children, 0, root.id);
  return out;
}

/** True if `maybeAncestorId` is `nodeId` or one of its ancestors within `root`. */
export function isSelfOrDescendant(root: TreeNode, nodeId: string, targetId: string): boolean {
  const find = (n: TreeNode): TreeNode | null => {
    if (n.id === nodeId) return n;
    for (const c of n.children) {
      const hit = find(c);
      if (hit) return hit;
    }
    return null;
  };
  const subtree = find(root);
  if (!subtree) return false;
  const contains = (n: TreeNode): boolean => n.id === targetId || n.children.some(contains);
  return contains(subtree);
}

/** Locate a node by id anywhere in the tree. */
export function findNode(root: TreeNode, id: string): TreeNode | null {
  if (root.id === id) return root;
  for (const c of root.children) {
    const hit = findNode(c, id);
    if (hit) return hit;
  }
  return null;
}

// --- Immutable mutations (for optimistic cache updates) -------------------- //

export function addChild(root: TreeNode, parentId: string, child: TreeNode): TreeNode {
  if (root.id === parentId) return { ...root, children: [...root.children, child] };
  return { ...root, children: root.children.map((c) => addChild(c, parentId, child)) };
}

export function updateNode(root: TreeNode, id: string, patch: Partial<TreeNode>): TreeNode {
  if (root.id === id) return { ...root, ...patch };
  return { ...root, children: root.children.map((c) => updateNode(c, id, patch)) };
}

export function removeNode(root: TreeNode, id: string): TreeNode {
  return {
    ...root,
    children: root.children.filter((c) => c.id !== id).map((c) => removeNode(c, id)),
  };
}

export function reparent(root: TreeNode, id: string, newParentId: string): TreeNode {
  const target = findNode(root, id);
  if (!target) return root;
  return addChild(removeNode(root, id), newParentId, { ...target, parentId: newParentId });
}
