import { type ReactNode, useCallback, useMemo, useState } from "react";

import { useShortcuts } from "@/lib/shortcuts";

import { createEditorBridge } from "@/modules/diff-review";
import type { TreeNode } from "@/modules/file-tree";
import type { ProjectIndex } from "@/modules/project-index";
import { type MatchTarget, SearchPanel, useProjectSearch } from "@/modules/project-search";

import { type DrawerTab, useDrawerTab } from "./outline-prefs";
import { findNodeByPath } from "./sync-decoration";
import type { useSourceJumps } from "./workspace-hooks";

export interface WorkspaceSearch {
  /** The panel, for the drawer's Search tab. */
  panel: ReactNode;
  /** The drawer's tab, held here so the shortcut can turn it to Search. */
  tab: DrawerTab;
  setTab: (tab: DrawerTab) => void;
}

/**
 * The project search of the editor screen (spec 122): the panel in the file drawer, fed by the project index, and
 * the shortcut that opens it (Ctrl+Shift+F, Cmd+Shift+F on a Mac). A replace writes through a short-lived collaboration provider per document, the path
 * the agent's accepted edits take, so everyone editing sees it at once. A viewer gets the search without replace.
 */
export function useWorkspaceSearch({
  projectId,
  treeRoot,
  index,
  readOnly,
  jumps,
  setFilesOpen,
}: {
  projectId: string;
  treeRoot: TreeNode | undefined;
  index: ProjectIndex;
  readOnly: boolean;
  jumps: ReturnType<typeof useSourceJumps>;
  setFilesOpen: (open: boolean) => void;
}): WorkspaceSearch {
  const [tab, setTab] = useDrawerTab();
  const [focusKey, setFocusKey] = useState(0);
  const openWriter = useMemo(() => {
    if (readOnly) return undefined;
    const resolve = (path: string) => {
      const node = treeRoot ? findNodeByPath(treeRoot, path) : null;
      return node?.type === "doc" ? node.id : null;
    };
    return () => createEditorBridge(projectId, resolve);
  }, [projectId, treeRoot, readOnly]);
  const state = useProjectSearch({ sources: index.texts, openWriter, onWritten: index.setDocText });

  useShortcuts({
    "mod+shift+f": () => {
      setFilesOpen(true);
      setTab("search");
      setFocusKey((key) => key + 1);
    },
  });

  const { onMatchJump } = jumps;
  const onOpen = useCallback(
    (target: MatchTarget) => {
      setFilesOpen(false);
      onMatchJump(target.path, target.line, { column: target.column, length: target.length });
    },
    [onMatchJump, setFilesOpen],
  );

  const panel = <SearchPanel state={state} status={index.status} onOpen={onOpen} focusKey={focusKey} />;
  return { panel, tab, setTab };
}
