import { useCallback, useMemo, useState } from "react";

import { FileTreeBody } from "./file-tree-body";
import type { FileTreeContextValue } from "./file-tree-context";
import { CreateEntityDialog, DeleteEntityDialog } from "./file-tree-dialogs";
import { FileTreeToolbar } from "./file-tree-toolbar";
import { UploadConflictDialog, UploadList } from "./file-tree-uploads-ui";
import { flattenVisible } from "./tree-utils";
import type { TreeEntity } from "./types";
import { resolveParentFolder, useExpandedIds } from "./use-expanded-ids";
import { useProjectTree } from "./use-file-tree";
import { useRovingRows } from "./use-roving-rows";
import { useTreeActions } from "./use-tree-actions";
import { useTreeDrag } from "./use-tree-drag";
import { useTreeKeyboard } from "./use-tree-keyboard";
import { useTreeSelection } from "./use-tree-selection";
import { useUploads } from "./use-uploads";

interface FileTreePanelProps {
  projectId: string;
  selectedId: string | null;
  onSelectEntity: (entity: TreeEntity) => void;
  /** Viewers / read-only collaborators see no file-tree mutation actions (spec 34 §5.3). */
  readOnly?: boolean;
}

function PanelDialogs({
  actions,
  uploads,
}: {
  actions: ReturnType<typeof useTreeActions>;
  uploads: ReturnType<typeof useUploads>;
}) {
  const { dialog } = actions;
  return (
    <>
      <CreateEntityDialog
        open={dialog?.kind === "create"}
        type={dialog?.kind === "create" ? dialog.createType : "doc"}
        onOpenChange={(v) => !v && actions.closeDialog()}
        onCreate={actions.confirmCreate}
      />
      <DeleteEntityDialog
        open={dialog?.kind === "delete"}
        node={dialog?.kind === "delete" ? dialog.node : null}
        onOpenChange={(v) => !v && actions.closeDialog()}
        onConfirm={actions.confirmDelete}
      />
      <UploadConflictDialog
        conflict={uploads.conflict}
        onCancel={() => uploads.setConflict(null)}
        onReplace={() => void uploads.onReplaceConflict()}
      />
    </>
  );
}

export function FileTreePanel({
  projectId,
  selectedId: selectedIdProp,
  onSelectEntity,
  readOnly = false,
}: FileTreePanelProps) {
  const treeQuery = useProjectTree(projectId);
  const root = treeQuery.data ?? null;

  const { expanded, toggle, expand, collapse } = useExpandedIds(projectId);
  const { selectedId, setSelectedId, select, activate } = useTreeSelection(
    selectedIdProp,
    onSelectEntity,
    toggle,
  );
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const uploads = useUploads(projectId);

  const flat = useMemo(() => (root ? flattenVisible(root, expanded) : []), [root, expanded]);
  const { focusedId, focusRow, registerRow } = useRovingRows(flat);

  const startRename = useCallback((id: string) => {
    // Defer so an open menu finishes closing (releasing focus) before the
    // inline input mounts and autofocuses — otherwise the close blurs it.
    setTimeout(() => setRenamingId(id), 0);
  }, []);

  const actions = useTreeActions({
    projectId,
    root,
    readOnly,
    selectedId,
    setSelectedId,
    expand,
    startRename,
    triggerUpload: uploads.triggerUpload,
  });
  const drag = useTreeDrag(root?.id ?? null, readOnly, actions.move);

  const onKeyDown = useTreeKeyboard({
    flat,
    focusedId,
    renamingId,
    readOnly,
    rootId: root?.id ?? null,
    expanded,
    focusRow,
    expand,
    collapse,
    activate,
    startRename,
    requestDelete: actions.requestDelete,
  });

  const ctx: FileTreeContextValue | null = root
    ? {
        selectedId,
        focusedId,
        expandedIds: expanded,
        renamingId,
        rootId: root.id,
        registerRow,
        onToggle: toggle,
        onSelect: select,
        onActivate: activate,
        onCommitRename: (id, name) => {
          setRenamingId(null);
          actions.commitRename(id, name);
        },
        onCancelRename: () => setRenamingId(null),
        onMenuAction: actions.onMenuAction,
        ...drag.row,
      }
    : null;

  return (
    <div className="flex h-full flex-col">
      <FileTreeToolbar
        readOnly={readOnly}
        hasRoot={!!root}
        onNewDoc={() => root && actions.openCreate("doc", resolveParentFolder(root, selectedId))}
        onNewFolder={() => root && actions.openCreate("folder", resolveParentFolder(root, selectedId))}
        onUpload={() => root && uploads.triggerUpload(resolveParentFolder(root, selectedId))}
      />

      <input
        ref={uploads.uploadInputRef}
        type="file"
        multiple
        className="hidden"
        aria-hidden
        onChange={(e) => e.target.files && uploads.onFilesPicked(e.target.files)}
      />

      <FileTreeBody
        query={treeQuery}
        ctx={ctx}
        readOnly={readOnly}
        onKeyDown={onKeyDown}
        onRootDragOver={drag.onRootDragOver}
        onRootDrop={drag.onRootDrop}
        onNewDoc={() => root && actions.openCreate("doc", root.id)}
        onUpload={() => root && uploads.triggerUpload(root.id)}
      />

      <UploadList uploads={uploads.uploads} onDismiss={uploads.dismissUpload} />

      <PanelDialogs actions={actions} uploads={uploads} />
    </div>
  );
}
