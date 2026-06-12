import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

import { FileTreeContext, type FileTreeContextValue } from "./file-tree-context";
import { FileTreeNode } from "./file-tree-node";
import { sortNodes } from "./tree-utils";
import type { TreeNode } from "./types";

/**
 * The scrollable body of the panel: loading skeletons, the error/retry state,
 * the empty-state, or the rendered ARIA tree. State decisions live in the panel;
 * this component only renders them.
 */
export function FileTreeBody({
  isLoading,
  isError,
  onRetry,
  ctx,
  root,
  readOnly,
  onKeyDown,
  onRootDragOver,
  onRootDrop,
  onNewDoc,
  onUpload,
}: {
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
  ctx: FileTreeContextValue | null;
  root: TreeNode | null;
  readOnly: boolean;
  onKeyDown: (e: React.KeyboardEvent) => void;
  onRootDragOver: (e: React.DragEvent) => void;
  onRootDrop: (e: React.DragEvent) => void;
  onNewDoc: () => void;
  onUpload: () => void;
}) {
  const { t } = useTranslation("files");
  return (
    <div className="flex-1 overflow-auto p-1">
      {isLoading && (
        <div className="space-y-2 p-1" aria-busy="true" aria-label={t("loadingFiles")}>
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-6 w-full" />
          ))}
        </div>
      )}

      {isError && (
        <div role="alert" className="space-y-2 p-3 text-center text-sm">
          <p className="text-destructive">{t("loadError")}</p>
          <Button variant="outline" size="sm" onClick={onRetry}>
            {t("common:action.retry")}
          </Button>
        </div>
      )}

      {ctx && root && (
        <FileTreeContext.Provider value={ctx}>
          {root.children.length === 0 ? (
            <div className="space-y-2 p-3 text-center text-sm text-muted-foreground">
              <p>{readOnly ? t("empty.readOnly") : t("empty.editable")}</p>
              {!readOnly && (
                <div className="flex justify-center gap-2">
                  <Button size="sm" variant="outline" onClick={onNewDoc}>
                    {t("action.newFile")}
                  </Button>
                  <Button size="sm" variant="outline" onClick={onUpload}>
                    {t("common:action.upload")}
                  </Button>
                </div>
              )}
            </div>
          ) : (
            <ul
              role="tree"
              aria-label={t("treeLabel")}
              className="select-none"
              onKeyDown={onKeyDown}
              onDragOver={onRootDragOver}
              onDrop={onRootDrop}
            >
              {sortNodes(root.children).map((child) => (
                <FileTreeNode key={child.id} node={child} depth={0} />
              ))}
            </ul>
          )}
        </FileTreeContext.Provider>
      )}
    </div>
  );
}
