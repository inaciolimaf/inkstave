import { useQuery } from "@tanstack/react-query";
import { useCallback, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import type { AgentRequest } from "@/modules/agent";
import { type TreeEntity, useProjectTree } from "@/modules/file-tree";
import type { Problem } from "@/modules/pdf-preview";
import { getProject, projectKey } from "@/modules/projects";

import type { MobileView } from "./mobile-tabs";
import { useSelectionFollowsTree } from "./selection-follows-tree";
import { useStartDocument } from "./start-document";
import type { LineSpan } from "./sync-decoration";
import type { EditorSelection } from "./use-editor-selection";
import type { useSourceSync } from "./use-source-sync";

/**
 * The project's file tree and name, and the document the screen opens on. The tree keeps the open file where it
 * moved when something other than the file drawer changed the tree (spec 107).
 */
export function useWorkspaceTree(
  projectId: string,
  selected: TreeEntity | null,
  onSelect: (entity: TreeEntity | null) => void,
) {
  const treeRoot = useProjectTree(projectId).data;
  const projectQuery = useQuery({
    queryKey: projectKey(projectId),
    queryFn: () => getProject(projectId),
  });
  const project = projectQuery.data;
  useStartDocument(treeRoot, project?.rootDocId, selected, onSelect);
  useSelectionFollowsTree(treeRoot, selected, onSelect);
  return { treeRoot, project };
}

/**
 * Flush pending local CRDT edits to the server before a compile materializes the content column
 * (spec 31 §5.4 / AC8). The open document's collab session registers its real `flush()` here; when no
 * session is active this resolves immediately.
 */
export function useFlushBeforeCompile() {
  const flushRef = useRef<(() => Promise<void>) | null>(null);
  return useCallback(async () => {
    await flushRef.current?.();
  }, []);
}

/** Following a link between the text and the PDF: a phone shows the side it lands on. */
export function useSourceJumps(sync: ReturnType<typeof useSourceSync>, setView: (view: MobileView) => void) {
  const { jumpToSource, handlePdfClick, handleSyncToPdf } = sync;
  const showPreview = useCallback(() => setView("preview"), [setView]);
  const onProblemJump = useCallback(
    (file: string, line: number) => {
      setView("content");
      jumpToSource(file, line);
    },
    [jumpToSource, setView],
  );
  const onPdfClick = useCallback(
    async (page: number, h: number, v: number) => {
      setView("content");
      await handlePdfClick(page, h, v);
    },
    [handlePdfClick, setView],
  );
  const onSyncToPdf = useCallback(() => {
    setView("preview");
    handleSyncToPdf();
  }, [handleSyncToPdf, setView]);
  // A search match jumps the same way, and selects the matched text (spec 122).
  const onMatchJump = useCallback(
    (file: string, line: number, span: LineSpan) => {
      setView("content");
      jumpToSource(file, line, span);
    },
    [jumpToSource, setView],
  );
  // The outline jumps the same way a problem does: the text shows, on a phone, and the line is revealed.
  return { showPreview, onProblemJump, onOutlineJump: onProblemJump, onMatchJump, onPdfClick, onSyncToPdf };
}

/** What the editor can ask the agent for: a word on a selection, or a fix for a compile error. */
export function useAgentAsks(openDoc: TreeEntity | null, setAgentOpen: (open: boolean) => void) {
  const { t } = useTranslation("editor");
  const [request, setRequest] = useState<AgentRequest | null>(null);
  const aboutSelection = ({ text, fromLine, toLine }: EditorSelection) => {
    if (!openDoc) return;
    setRequest({ quote: { path: openDoc.path, fromLine, toLine, text } });
    setAgentOpen(true);
  };
  const aboutProblem = (problem: Problem) => {
    const where = problem.file ? ` (${problem.file}:${problem.line})` : "";
    setRequest({ send: t("problemPrompt", { message: problem.message, where }) });
    setAgentOpen(true);
  };
  return { request, aboutSelection, aboutProblem };
}

/** Which of the bar's dialogs is open: share and history. */
export function useWorkspaceDialogs() {
  const [shareOpen, setShareOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  return { shareOpen, setShareOpen, historyOpen, setHistoryOpen };
}
