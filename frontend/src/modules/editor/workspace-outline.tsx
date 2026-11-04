import { type ReactNode, useMemo } from "react";

import { useMediaQuery } from "@/lib/use-media-query";
import type { TreeNode } from "@/modules/file-tree";
import { type ProjectIndex, useProjectIndex } from "@/modules/project-index";

import { OutlinePanel } from "./outline-panel";
import { useOutlinePinned } from "./outline-prefs";
import { pickStartDocument } from "./start-document";
import type { useSourceJumps } from "./workspace-hooks";
import type { useSourceSync } from "./use-source-sync";
import { type WorkspaceSearch, useWorkspaceSearch } from "./workspace-search";

export interface WorkspaceOutline {
  /** The panel, for the drawer's tab. */
  panel: ReactNode;
  /** The panel pinned left of the text, on a wide desktop when the writer pinned it. */
  pinnedColumn: ReactNode;
  /** The project index, which the LaTeX completion reads too (spec 112). */
  index: ProjectIndex;
  /** The project search, the drawer's third tab, fed by the same index (spec 122). */
  search: WorkspaceSearch;
}

/**
 * The outline of the editor screen (spec 111): the panel for the drawer's tab, and on a wide desktop the same panel
 * pinned as a narrow column left of the text. Jumping to an entry shows the text and reveals its line. The project
 * search reads the same index, so it is built here too (spec 122).
 */
export function useWorkspaceOutline({
  projectId,
  treeRoot,
  project,
  sync,
  jumps,
  setFilesOpen,
  readOnly,
}: {
  projectId: string;
  treeRoot: TreeNode | undefined;
  /** The project, for its root document; undefined while it loads. */
  project: { rootDocId?: string | null } | undefined;
  sync: ReturnType<typeof useSourceSync>;
  jumps: ReturnType<typeof useSourceJumps>;
  setFilesOpen: (open: boolean) => void;
  readOnly: boolean;
}): WorkspaceOutline {
  const wideDesk = useMediaQuery("(min-width: 1280px)");
  const [pinned, togglePinned] = useOutlinePinned();
  const openDoc = sync.openDoc;
  const openDocId = openDoc?.type === "doc" ? openDoc.id : null;
  const rootDocId = project?.rootDocId;
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
  const search = useWorkspaceSearch({ projectId, treeRoot, index, readOnly, jumps, setFilesOpen });
  return { panel, pinnedColumn, index, search };
}
