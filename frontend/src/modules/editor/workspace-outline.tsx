import { type ReactNode, useMemo } from "react";

import { useMediaQuery } from "@/lib/use-media-query";
import type { TreeNode } from "@/modules/file-tree";
import { type ProjectIndex, useProjectIndex } from "@/modules/project-index";

import { OutlinePanel } from "./outline-panel";
import { useOutlinePinned } from "./outline-prefs";
import { pickStartDocument } from "./start-document";
import type { useSourceJumps } from "./workspace-hooks";
import type { useSourceSync } from "./use-source-sync";

export interface WorkspaceOutline {
  /** The panel, for the drawer's tab. */
  panel: ReactNode;
  /** The panel pinned left of the text, on a wide desktop when the writer pinned it. */
  pinnedColumn: ReactNode;
  /** The project index, which the LaTeX completion reads too (spec 112). */
  index: ProjectIndex;
}

/**
 * The outline of the editor screen (spec 111): the panel for the drawer's tab, and on a wide desktop the same panel
 * pinned as a narrow column left of the text. Jumping to an entry shows the text and reveals its line.
 */
export function useWorkspaceOutline({
  projectId,
  treeRoot,
  rootDocId,
  sync,
  jumps,
  setFilesOpen,
}: {
  projectId: string;
  treeRoot: TreeNode | undefined;
  rootDocId: string | null | undefined;
  sync: ReturnType<typeof useSourceSync>;
  jumps: ReturnType<typeof useSourceJumps>;
  setFilesOpen: (open: boolean) => void;
}): WorkspaceOutline {
  const wideDesk = useMediaQuery("(min-width: 1280px)");
  const [pinned, togglePinned] = useOutlinePinned();
  const openDoc = sync.openDoc;
  const openDocId = openDoc?.type === "doc" ? openDoc.id : null;
  const mainDocId = useMemo(
    () => (treeRoot ? (pickStartDocument(treeRoot, rootDocId ?? null)?.id ?? null) : null),
    [treeRoot, rootDocId],
  );
  const index: ProjectIndex = useProjectIndex({
    projectId,
    root: treeRoot,
    mainDocId,
    openDocId,
    view: sync.editorView,
  });

  const panel = (
    <OutlinePanel
      entries={index.entries}
      status={index.status}
      openDocId={openDocId}
      cursorLine={index.cursorLine}
      onOpen={(entry) => {
        setFilesOpen(false);
        jumps.onOutlineJump(entry.path, entry.line);
      }}
      pin={wideDesk ? { pinned, onToggle: togglePinned } : undefined}
    />
  );
  const pinnedColumn =
    pinned && wideDesk ? (
      <div className="h-full w-56 shrink-0 border-r border-control-edge">{panel}</div>
    ) : null;
  return { panel, pinnedColumn, index };
}
