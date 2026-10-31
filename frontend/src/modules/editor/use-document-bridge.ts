import { useEffect, useMemo } from "react";

import { config } from "@/config";
import { createEditorBridge } from "@/modules/diff-review";
import type { TreeNode } from "@/modules/file-tree";

import { findNodeByPath } from "./sync-decoration";

export function useDocumentBridge(projectId: string, treeRoot: TreeNode | undefined) {
  const documentBridge = useMemo(
    () =>
      config.agentEnabled && config.collabWsUrl
        ? createEditorBridge(projectId, (path) =>
            treeRoot ? (findNodeByPath(treeRoot, path)?.id ?? null) : null,
          )
        : undefined,
    [projectId, treeRoot],
  );
  useEffect(() => () => documentBridge?.destroy?.(), [documentBridge]);
  return documentBridge;
}
