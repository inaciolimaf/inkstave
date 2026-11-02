import type { EditorView } from "@codemirror/view";
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import type { TreeEntity, TreeNode } from "@/modules/file-tree";
import { useProblems, useSyncTex } from "@/modules/pdf-preview";

import { applyDiagnostics } from "./diagnostics";
import { cursorLine, findNodeByPath, revealLine } from "./sync-decoration";

/** Ties the open document to the PDF: SyncTeX both ways, jumps to a source line, and diagnostics. */
export function useSourceSync(
  projectId: string,
  selected: TreeEntity | null,
  onSelect: (entity: TreeEntity) => void,
  treeRoot: TreeNode | undefined,
) {
  const { t } = useTranslation("editor");
  const [openDoc, setOpenDoc] = useState<TreeEntity | null>(null);
  const [syncCompileId, setSyncCompileId] = useState<string | null>(null);
  const [problemsKey, setProblemsKey] = useState<string>("latest");
  const [editorView, setEditorView] = useState<EditorView | null>(null);
  const { pdfTarget, syncFromSource, syncFromPdf } = useSyncTex(projectId, syncCompileId);
  const problemsState = useProblems(projectId, problemsKey);
  const viewRef = useRef<EditorView | null>(null);
  const pendingReveal = useRef<{ path: string; line: number } | null>(null);

  // Track the currently-open document (the last selected non-folder doc).
  useEffect(() => {
    if (selected && selected.type === "doc") setOpenDoc(selected);
  }, [selected]);

  const handleEditorView = useCallback((view: EditorView | null) => {
    viewRef.current = view;
    setEditorView(view);
  }, []);

  // Push inline diagnostics for the open file; refresh on each compile / file switch.
  useEffect(() => {
    if (!editorView) return;
    const path = openDoc?.path;
    const forFile =
      problemsState.problems && path ? problemsState.problems.problems.filter((p) => p.file === path) : [];
    applyDiagnostics(editorView, forFile);
  }, [editorView, openDoc, problemsState.problems]);

  // Reveal a source location, opening a different document first if needed.
  const jumpToSource = useCallback(
    (file: string, line: number) => {
      if (openDoc?.path === file && viewRef.current) {
        revealLine(viewRef.current, line);
        return;
      }
      const node = treeRoot ? findNodeByPath(treeRoot, file) : null;
      if (node && node.type === "doc") {
        pendingReveal.current = { path: file, line };
        onSelect(node);
      } else {
        toast.message(t("toolbar.notInProject"));
      }
    },
    [openDoc, treeRoot, onSelect, t],
  );

  // After a cross-file jump, reveal the line once the new document has loaded.
  const handleDocumentLoaded = useCallback((entity: TreeEntity) => {
    const pending = pendingReveal.current;
    if (pending && pending.path === entity.path && viewRef.current) {
      revealLine(viewRef.current, pending.line);
      pendingReveal.current = null;
    }
  }, []);

  // Forward sync (editor -> PDF): cursor line of the open doc -> PDF box.
  const handleSyncToPdf = useCallback(() => {
    const view = viewRef.current;
    if (!view || openDoc?.type !== "doc") return;
    void syncFromSource(openDoc.path, cursorLine(view));
  }, [openDoc, syncFromSource]);

  // Inverse sync (PDF -> editor): resolve the point, then reveal / open + reveal.
  const handlePdfClick = useCallback(
    async (page: number, h: number, v: number) => {
      const location = await syncFromPdf(page, h, v);
      if (location) jumpToSource(location.file, location.line);
    },
    [syncFromPdf, jumpToSource],
  );

  const handleCompileResult = useCallback((compileId: string | null) => {
    setProblemsKey(compileId ?? "latest");
  }, []);

  return {
    openDoc,
    editorView,
    syncCompileId,
    setSyncCompileId,
    pdfTarget,
    problemsState,
    handleEditorView,
    jumpToSource,
    handleDocumentLoaded,
    handleSyncToPdf,
    handlePdfClick,
    handleCompileResult,
  };
}
