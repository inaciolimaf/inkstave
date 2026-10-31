import { useCallback, useEffect, useState } from "react";

import type { TreeEntity, TreeNode } from "./types";

/** The selected row, kept in step with the parent's selection. */
export function useTreeSelection(
  selectedIdProp: string | null,
  onSelectEntity: (entity: TreeEntity) => void,
  toggle: (id: string) => void,
) {
  const [selectedId, setSelectedId] = useState<string | null>(selectedIdProp);
  useEffect(() => setSelectedId(selectedIdProp), [selectedIdProp]);

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

  return { selectedId, setSelectedId, select, activate };
}
