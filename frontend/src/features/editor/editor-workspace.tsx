import type { EditorView } from "@codemirror/view";
import { History, Share2, Sparkles } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import { AgentPanel } from "@/features/agent/AgentPanel";
import { createEditorBridge } from "@/features/diff-review/editor-bridge";
import { HistoryPanel } from "@/features/history/HistoryPanel";
import { ShareDialog } from "@/features/sharing/ShareDialog";
import { FileTreePanel } from "@/features/file-tree/file-tree-panel";
import type { TreeEntity } from "@/features/file-tree/types";
import { useProjectTree } from "@/features/file-tree/use-file-tree";
import { PreviewPane } from "@/features/pdf-preview/PreviewPane";
import { useProblems } from "@/features/pdf-preview/hooks/useProblems";
import { useSyncTex } from "@/features/pdf-preview/hooks/useSyncTex";
import { useMediaQuery } from "@/lib/use-media-query";

import { useAuth } from "@/auth/auth-context";
import { isReadOnly, usePermissions } from "@/features/sharing/usePermissions";
import { NotificationsBell } from "@/features/notifications/NotificationsBell";
import { config } from "@/config";
import { tokenStore } from "@/lib/token-store";

import { applyDiagnostics } from "./diagnostics";
import { EditorPane } from "./editor-pane";
import { cursorLine, findNodeByPath, revealLine } from "./sync-decoration";
import { UnsavedChangesGuard } from "./unsaved-changes-guard";

const COLLAB_ENABLED = Boolean(config.collabWsUrl);
const getCollabToken = () => tokenStore.getAccessToken() ?? "";

export function EditorWorkspace({ projectId }: { projectId: string }) {
  const [selected, setSelected] = useState<TreeEntity | null>(null);
  const [dirty, setDirty] = useState(false);
  const [openDoc, setOpenDoc] = useState<TreeEntity | null>(null);
  const [syncCompileId, setSyncCompileId] = useState<string | null>(null);
  const [problemsKey, setProblemsKey] = useState<string>("latest");
  const [editorView, setEditorView] = useState<EditorView | null>(null);
  const wide = useMediaQuery("(min-width: 768px)");

  const tree = useProjectTree(projectId);
  const { pdfTarget, syncFromSource, syncFromPdf } = useSyncTex(projectId, syncCompileId);
  const problemsState = useProblems(projectId, problemsKey);
  const { user } = useAuth();
  const currentUser = user ? { id: user.id, name: user.display_name } : null;
  const permissions = usePermissions(projectId);
  const readOnly = isReadOnly(permissions.data);
  const [shareOpen, setShareOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const agentKey = `inkstave.agent.open.${projectId}`;
  const [agentOpen, setAgentOpen] = useState(() => {
    try {
      return localStorage.getItem(agentKey) === "1";
    } catch {
      return false;
    }
  });
  useEffect(() => {
    try {
      localStorage.setItem(agentKey, agentOpen ? "1" : "0");
    } catch {
      // ignore storage failures
    }
  }, [agentKey, agentOpen]);

  const treeRoot = tree.data;
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

  const viewRef = useRef<EditorView | null>(null);
  const pendingReveal = useRef<{ path: string; line: number } | null>(null);

  // Flush pending local CRDT edits to the server before a compile materializes the
  // content column (spec 31 §5.4 / AC8). The open document's collab session registers
  // its real `flush()` here; when no session is active this resolves immediately.
  const flushRef = useRef<(() => Promise<void>) | null>(null);
  const flushBeforeCompile = useCallback(async () => {
    await flushRef.current?.();
  }, []);

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
      problemsState.problems && path
        ? problemsState.problems.problems.filter((p) => p.file === path)
        : [];
    applyDiagnostics(editorView, forFile);
  }, [editorView, openDoc, problemsState.problems]);

  // Reveal a source location, opening a different document first if needed.
  const jumpToSource = useCallback(
    (file: string, line: number) => {
      if (openDoc?.path === file && viewRef.current) {
        revealLine(viewRef.current, line);
        return;
      }
      const root = tree.data;
      const node = root ? findNodeByPath(root, file) : null;
      if (node && node.type === "doc") {
        pendingReveal.current = { path: file, line };
        setSelected(node);
      } else {
        toast.message(`Open ${file} to jump there`);
      }
    },
    [openDoc, tree.data],
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

  return (
    <>
      <div className="flex items-center gap-2 border-b px-3 py-1.5">
        {config.agentEnabled && (
          <Button
            size="sm"
            variant={agentOpen ? "secondary" : "outline"}
            className="ml-auto"
            aria-pressed={agentOpen}
            onClick={() => setAgentOpen((v) => !v)}
          >
            <Sparkles aria-hidden="true" className="size-4" />
            Agent
          </Button>
        )}
        <Button
          size="sm"
          variant="outline"
          className={config.agentEnabled ? undefined : "ml-auto"}
          disabled={openDoc?.type !== "doc"}
          onClick={() => setHistoryOpen(true)}
        >
          <History aria-hidden="true" className="size-4" />
          History
        </Button>
        <Button size="sm" variant="outline" onClick={() => setShareOpen(true)}>
          <Share2 aria-hidden="true" className="size-4" />
          Share
        </Button>
        <NotificationsBell />
      </div>
      <ShareDialog projectId={projectId} open={shareOpen} onOpenChange={setShareOpen} />
      {config.agentEnabled && (
        <AgentPanel
          projectId={projectId}
          open={agentOpen}
          onOpenChange={setAgentOpen}
          documentBridge={documentBridge}
          onBeforeSend={flushBeforeCompile}
          onReviewProposal={() => {
            // The diff-review surface (spec 47) opens inside the panel via documentBridge.
          }}
        />
      )}
      {openDoc?.type === "doc" && (
        <HistoryPanel
          projectId={projectId}
          docId={openDoc.id}
          open={historyOpen}
          onOpenChange={setHistoryOpen}
        />
      )}
      <ResizablePanelGroup
        direction={wide ? "horizontal" : "vertical"}
        autoSaveId={`inkstave:panes:${projectId}`}
        className="min-h-0 flex-1"
      >
        <ResizablePanel defaultSize={22} minSize={12} className="min-h-0">
          <FileTreePanel
            projectId={projectId}
            selectedId={selected?.id ?? null}
            onSelectEntity={setSelected}
            readOnly={readOnly}
          />
        </ResizablePanel>
        <ResizableHandle withHandle />
        <ResizablePanel defaultSize={48} minSize={20} className="min-h-0">
          <EditorPane
            projectId={projectId}
            selected={selected}
            onClearSelection={() => setSelected(null)}
            onDirtyChange={setDirty}
            onEditorView={handleEditorView}
            onSyncToPdf={handleSyncToPdf}
            onDocumentLoaded={handleDocumentLoaded}
            syncEnabled={syncCompileId !== null}
            collabEnabled={COLLAB_ENABLED}
            getToken={getCollabToken}
            currentUser={currentUser}
            readOnly={readOnly}
          />
        </ResizablePanel>
        <ResizableHandle withHandle />
        <ResizablePanel defaultSize={30} minSize={0} className="min-h-0">
          <PreviewPane
            projectId={projectId}
            flush={flushBeforeCompile}
            onActiveCompileChange={setSyncCompileId}
            onPdfClick={handlePdfClick}
            syncTarget={pdfTarget}
            onCompileResult={handleCompileResult}
            problems={problemsState.problems}
            problemsLoading={problemsState.loading}
            problemsReason={problemsState.reason}
            onProblemJump={jumpToSource}
          />
        </ResizablePanel>
      </ResizablePanelGroup>
      <UnsavedChangesGuard when={dirty} />
    </>
  );
}
