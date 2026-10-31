import { useState } from "react";

import type { TreeNode } from "./types";

/** Drag state and handlers: `row` goes into the tree context, the rest on the tree's root. */
export function useTreeDrag(
  rootId: string | null,
  readOnly: boolean,
  move: (id: string, newParentId: string) => void,
) {
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [dropTargetId, setDropTargetId] = useState<string | null>(null);

  const row = {
    draggingId,
    dropTargetId,
    onDragStart: (id: string) => !readOnly && setDraggingId(id),
    onDragEnterNode: (node: TreeNode) => setDropTargetId(node.id),
    onDropOnNode: (node: TreeNode) => {
      setDropTargetId(null);
      if (draggingId) move(draggingId, node.id);
      setDraggingId(null);
    },
    onDragEnd: () => {
      setDraggingId(null);
      setDropTargetId(null);
    },
  };

  const onRootDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    if (rootId) setDropTargetId(rootId);
  };

  const onRootDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDropTargetId(null);
    if (rootId && draggingId) move(draggingId, rootId);
    setDraggingId(null);
  };

  return { row, onRootDragOver, onRootDrop };
}
