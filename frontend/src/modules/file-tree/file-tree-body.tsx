import type { UseQueryResult } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { ErrorState, QueryView } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

import { FileTreeContext, type FileTreeContextValue } from "./file-tree-context";
import { FileTreeNode } from "./file-tree-node";
import { sortNodes } from "./tree-utils";
import type { TreeNode } from "./types";

const ERROR_CLASS = "flex-col p-3 text-center";

function TreeSkeleton() {
  const { t } = useTranslation("files");
  return (
    <div className="space-y-2 p-1" aria-busy="true" aria-label={t("loadingFiles")}>
      {Array.from({ length: 5 }).map((_, i) => (
        <Skeleton key={i} className="h-6 w-full" />
      ))}
    </div>
  );
}

function EmptyTree({
  readOnly,
  onNewDoc,
  onUpload,
}: {
  readOnly: boolean;
  onNewDoc: () => void;
  onUpload: () => void;
}) {
  const { t } = useTranslation("files");
  return (
    <div className="space-y-2 p-3 text-center text-body text-muted-foreground">
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
  );
}

/**
 * The scrollable body of the panel: loading skeletons, the error/retry state,
 * the empty-state, or the rendered ARIA tree. State decisions live in the panel;
 * this component only renders them.
 */
export function FileTreeBody({
  query,
  ctx,
  readOnly,
  onKeyDown,
  onRootDragOver,
  onRootDrop,
  onNewDoc,
  onUpload,
}: {
  query: UseQueryResult<TreeNode>;
  ctx: FileTreeContextValue | null;
  readOnly: boolean;
  onKeyDown: (e: React.KeyboardEvent) => void;
  onRootDragOver: (e: React.DragEvent) => void;
  onRootDrop: (e: React.DragEvent) => void;
  onNewDoc: () => void;
  onUpload: () => void;
}) {
  const { t } = useTranslation("files");
  // A failed background refetch keeps the tree on screen, with the error above it.
  const staleError = query.isError && query.data !== undefined;
  return (
    <div className="flex-1 overflow-auto p-1">
      {staleError && (
        <ErrorState message={t("loadError")} className={ERROR_CLASS} onRetry={() => void query.refetch()} />
      )}
      <QueryView
        query={{ ...query, isError: query.isError && !staleError }}
        loading={<TreeSkeleton />}
        errorMessage={t("loadError")}
        errorClassName={ERROR_CLASS}
      >
        {(root) =>
          ctx && (
            <FileTreeContext.Provider value={ctx}>
              {root.children.length === 0 ? (
                <EmptyTree readOnly={readOnly} onNewDoc={onNewDoc} onUpload={onUpload} />
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
          )
        }
      </QueryView>
    </div>
  );
}
