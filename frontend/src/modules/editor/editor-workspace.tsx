import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Desk } from "@/components/manuscript";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import { config } from "@/config";
import { tokenStore } from "@/lib/token-store";
import { useMediaQuery } from "@/lib/use-media-query";
import { AgentPanel } from "@/modules/agent";
import { useAuth } from "@/modules/auth";
import { createEditorBridge } from "@/modules/diff-review";
import { FileTreePanel, useProjectTree } from "@/modules/file-tree";
import type { TreeEntity, TreeNode } from "@/modules/file-tree";
import { HistoryPanel } from "@/modules/history";
import { PreviewPane } from "@/modules/pdf-preview";
import { getProject, projectKey } from "@/modules/projects";
import { ShareDialog, isReadOnly, usePermissions } from "@/modules/sharing";

import { EditorBar } from "./editor-bar";
import { EditorPane } from "./editor-pane";
import { findNodeByPath } from "./sync-decoration";
import { UnsavedChangesGuard } from "./unsaved-changes-guard";
import { useAgentOpen } from "./use-agent-open";
import { useSourceSync } from "./use-source-sync";

const COLLAB_ENABLED = Boolean(config.collabWsUrl);
const getCollabToken = () => tokenStore.getAccessToken() ?? "";

function useDocumentBridge(projectId: string, treeRoot: TreeNode | undefined) {
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

/** The panels that slide over the workspace. */
function WorkspaceDrawers({
  projectId,
  openDoc,
  agentOpen,
  onAgentOpenChange,
  documentBridge,
  onBeforeSend,
  historyOpen,
  onHistoryOpenChange,
}: {
  projectId: string;
  openDoc: TreeEntity | null;
  agentOpen: boolean;
  onAgentOpenChange: (open: boolean) => void;
  documentBridge: ReturnType<typeof useDocumentBridge>;
  onBeforeSend: () => Promise<void>;
  historyOpen: boolean;
  onHistoryOpenChange: (open: boolean) => void;
}) {
  return (
    <>
      {config.agentEnabled && (
        <AgentPanel
          projectId={projectId}
          open={agentOpen}
          onOpenChange={onAgentOpenChange}
          documentBridge={documentBridge}
          onBeforeSend={onBeforeSend}
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
          onOpenChange={onHistoryOpenChange}
        />
      )}
    </>
  );
}

/** The whole editor screen: the one bar, the side panels and the three resizable panes. */
export function EditorWorkspace({ projectId }: { projectId: string }) {
  const [selected, setSelected] = useState<TreeEntity | null>(null);
  const [dirty, setDirty] = useState(false);
  const wide = useMediaQuery("(min-width: 768px)");

  const tree = useProjectTree(projectId);
  const treeRoot = tree.data;
  const sync = useSourceSync(projectId, selected, setSelected, treeRoot);
  const { user } = useAuth();
  const currentUser = user ? { id: user.id, name: user.display_name } : null;
  const permissions = usePermissions(projectId);
  const readOnly = isReadOnly(permissions.data);
  const projectQuery = useQuery({
    queryKey: projectKey(projectId),
    queryFn: () => getProject(projectId),
  });
  const [shareOpen, setShareOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [agentOpen, setAgentOpen] = useAgentOpen(projectId);
  const documentBridge = useDocumentBridge(projectId, treeRoot);

  // Flush pending local CRDT edits to the server before a compile materializes the
  // content column (spec 31 §5.4 / AC8). The open document's collab session registers
  // its real `flush()` here; when no session is active this resolves immediately.
  const flushRef = useRef<(() => Promise<void>) | null>(null);
  const flushBeforeCompile = useCallback(async () => {
    await flushRef.current?.();
  }, []);

  return (
    <Desk
      bar={
        <EditorBar
          projectId={projectId}
          projectName={projectQuery.data?.name}
          agentOpen={agentOpen}
          onToggleAgent={() => setAgentOpen((v) => !v)}
          historyDisabled={sync.openDoc?.type !== "doc"}
          onOpenHistory={() => setHistoryOpen(true)}
          onOpenShare={() => setShareOpen(true)}
        />
      }
    >
      <ShareDialog projectId={projectId} open={shareOpen} onOpenChange={setShareOpen} />
      <WorkspaceDrawers
        projectId={projectId}
        openDoc={sync.openDoc}
        agentOpen={agentOpen}
        onAgentOpenChange={setAgentOpen}
        documentBridge={documentBridge}
        onBeforeSend={flushBeforeCompile}
        historyOpen={historyOpen}
        onHistoryOpenChange={setHistoryOpen}
      />
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
        <ResizableHandle />
        <ResizablePanel defaultSize={48} minSize={20} className="min-h-0">
          <EditorPane
            projectId={projectId}
            selected={selected}
            onClearSelection={() => setSelected(null)}
            onDirtyChange={setDirty}
            onEditorView={sync.handleEditorView}
            onSyncToPdf={sync.handleSyncToPdf}
            onDocumentLoaded={sync.handleDocumentLoaded}
            syncEnabled={sync.syncCompileId !== null}
            collabEnabled={COLLAB_ENABLED}
            getToken={getCollabToken}
            currentUser={currentUser}
            readOnly={readOnly}
          />
        </ResizablePanel>
        <ResizableHandle />
        <ResizablePanel defaultSize={30} minSize={0} className="min-h-0">
          <PreviewPane
            projectId={projectId}
            flush={flushBeforeCompile}
            onActiveCompileChange={sync.setSyncCompileId}
            onPdfClick={sync.handlePdfClick}
            syncTarget={sync.pdfTarget}
            onCompileResult={sync.handleCompileResult}
            problems={sync.problemsState.problems}
            problemsLoading={sync.problemsState.loading}
            problemsReason={sync.problemsState.reason}
            onProblemJump={sync.jumpToSource}
          />
        </ResizablePanel>
      </ResizablePanelGroup>
      <UnsavedChangesGuard when={dirty} />
    </Desk>
  );
}
