import { type ReactNode, useState } from "react";

import { Desk } from "@/components/manuscript";
import { config } from "@/config";
import { tokenStore } from "@/lib/token-store";
import { useMediaQuery } from "@/lib/use-media-query";
import { useAuth } from "@/modules/auth";
import { FileTreePanel, useProjectTree } from "@/modules/file-tree";
import type { TreeEntity } from "@/modules/file-tree";
import { PreviewPane } from "@/modules/pdf-preview";
import type { Problem } from "@/modules/pdf-preview";
import { ShareDialog } from "@/modules/sharing";

import { AskAgentButton } from "./ask-agent-button";
import { ContentPane } from "./content-pane";
import { EditorBar } from "./editor-bar";
import { MobileTabs, type MobileView } from "./mobile-tabs";
import { UnsavedChangesGuard } from "./unsaved-changes-guard";
import { useAgentOpen } from "./use-agent-open";
import { useEditorSelection, type EditorSelection } from "./use-editor-selection";
import { useAgentAsks, useFlushBeforeCompile, useSourceJumps } from "./workspace-hooks";
import { Panes } from "./workspace-panes";
import { WorkspaceDrawers } from "./workspace-drawers";
import { useProposalReview } from "./use-proposal-review";
import { useWorkspaceProject } from "./use-workspace-project";
import { useSourceSync } from "./use-source-sync";

const COLLAB_ENABLED = Boolean(config.collabWsUrl);
const getCollabToken = () => tokenStore.getAccessToken() ?? "";

/** The hosts in the bar and the status line that the panes render their controls into. */
function useSlots() {
  const [compile, setCompile] = useState<HTMLElement | null>(null);
  const [output, setOutput] = useState<HTMLElement | null>(null);
  const [status, setStatus] = useState<HTMLElement | null>(null);
  return { compile, setCompile, output, setOutput, status, setStatus };
}

function SelectionAsk({
  selection,
  clear,
  wide,
  asks,
}: {
  selection: EditorSelection | null;
  clear: () => void;
  wide: boolean;
  asks: ReturnType<typeof useAgentAsks>;
}) {
  if (!config.agentEnabled || !selection) return null;
  return (
    <AskAgentButton
      selection={selection}
      floating={wide}
      onAsk={() => {
        asks.aboutSelection(selection);
        clear();
      }}
    />
  );
}

/** The PDF pane, wired to the bar and the status line, where its controls live. */
function WorkspacePreview({
  projectId,
  flush,
  sync,
  jumps,
  onProblemAsk,
  compileSlot,
  outputSlot,
}: {
  projectId: string;
  flush: () => Promise<void>;
  sync: ReturnType<typeof useSourceSync>;
  jumps: ReturnType<typeof useSourceJumps>;
  onProblemAsk: (problem: Problem) => void;
  compileSlot: HTMLElement | null;
  outputSlot: HTMLElement | null;
}) {
  return (
    <PreviewPane
      projectId={projectId}
      flush={flush}
      onActiveCompileChange={sync.setSyncCompileId}
      onPdfClick={jumps.onPdfClick}
      syncTarget={sync.pdfTarget}
      onCompileResult={sync.handleCompileResult}
      onCompileSucceeded={jumps.showPreview}
      problems={sync.problemsState.problems}
      problemsLoading={sync.problemsState.loading}
      problemsReason={sync.problemsState.reason}
      onProblemJump={jumps.onProblemJump}
      onProblemAsk={config.agentEnabled ? onProblemAsk : undefined}
      compileSlot={compileSlot}
      outputSlot={outputSlot}
    />
  );
}

/** The text pane, wired to the open project. */
function WorkspaceContent({
  projectId,
  selected,
  onSelect,
  onDirtyChange,
  sync,
  onSyncToPdf,
  readOnly,
  filesOpen,
  setFilesOpen,
  slots,
  reviewBar,
}: {
  projectId: string;
  selected: TreeEntity | null;
  onSelect: (entity: TreeEntity | null) => void;
  onDirtyChange: (dirty: boolean) => void;
  sync: ReturnType<typeof useSourceSync>;
  onSyncToPdf: () => void;
  readOnly: boolean;
  filesOpen: boolean;
  setFilesOpen: (open: boolean) => void;
  slots: ReturnType<typeof useSlots>;
  reviewBar: ReactNode;
}) {
  const { user } = useAuth();
  const pickFile = (entity: TreeEntity) => {
    onSelect(entity);
    if (entity.type !== "folder") setFilesOpen(false);
  };
  return (
    <ContentPane
      editor={{
        projectId,
        selected,
        onClearSelection: () => onSelect(null),
        onDirtyChange,
        onEditorView: sync.handleEditorView,
        onSyncToPdf,
        onDocumentLoaded: sync.handleDocumentLoaded,
        syncEnabled: sync.syncCompileId !== null,
        collabEnabled: COLLAB_ENABLED,
        getToken: getCollabToken,
        currentUser: user ? { id: user.id, name: user.display_name } : null,
        readOnly,
        statusSlot: slots.status,
      }}
      reviewBar={reviewBar}
      filesOpen={filesOpen}
      onOpenFiles={() => setFilesOpen(true)}
      onCloseFiles={() => setFilesOpen(false)}
      fileTree={
        <FileTreePanel
          projectId={projectId}
          selectedId={selected?.id ?? null}
          onSelectEntity={pickFile}
          readOnly={readOnly}
        />
      }
      statusSlotRef={slots.setStatus}
      outputSlotRef={slots.setOutput}
    />
  );
}

/** The whole editor screen (spec 107): one bar, the text and the PDF, and the rest on demand. */
export function EditorWorkspace({ projectId }: { projectId: string }) {
  const [selected, setSelected] = useState<TreeEntity | null>(null);
  const [dirty, setDirty] = useState(false);
  const wide = useMediaQuery("(min-width: 768px)");
  const [view, setView] = useState<MobileView>("content");
  const [filesOpen, setFilesOpen] = useState(false);
  const slots = useSlots();

  const { data: treeRoot } = useProjectTree(projectId);
  const sync = useSourceSync(projectId, selected, setSelected, treeRoot);
  const { projectQuery, readOnly } = useWorkspaceProject(projectId, treeRoot, selected, setSelected);
  const [shareOpen, setShareOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [agentOpen, setAgentOpen] = useAgentOpen(projectId);
  const { selection, clearSelection } = useEditorSelection(sync.editorView);
  const asks = useAgentAsks(sync.openDoc, setAgentOpen);
  const jumps = useSourceJumps(sync, setView);

  const proposals = useProposalReview({
    projectId,
    sync,
    treeRoot,
    readOnly,
    wide,
    setSelected,
    setView,
  });
  const flushBeforeCompile = useFlushBeforeCompile();

  const content = (
    <WorkspaceContent
      projectId={projectId}
      selected={selected}
      onSelect={setSelected}
      onDirtyChange={setDirty}
      sync={sync}
      onSyncToPdf={jumps.onSyncToPdf}
      readOnly={readOnly}
      filesOpen={filesOpen}
      setFilesOpen={setFilesOpen}
      slots={slots}
      reviewBar={proposals.reviewBar}
    />
  );

  return (
    <Desk
      bar={
        <EditorBar
          projectId={projectId}
          projectName={projectQuery.data?.name}
          fileName={sync.openDoc?.name}
          onOpenFiles={() => setFilesOpen((v) => !v)}
          compileSlotRef={slots.setCompile}
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
        agentRequest={asks.request}
        proposalStatuses={proposals.proposalStatuses}
        onReviewProposal={proposals.open}
        onBeforeSend={flushBeforeCompile}
        historyOpen={historyOpen}
        onHistoryOpenChange={setHistoryOpen}
      />
      <Panes
        projectId={projectId}
        wide={wide}
        view={view}
        content={content}
        preview={
          <WorkspacePreview
            projectId={projectId}
            flush={flushBeforeCompile}
            sync={sync}
            jumps={jumps}
            onProblemAsk={asks.aboutProblem}
            compileSlot={slots.compile}
            outputSlot={slots.output}
          />
        }
      />
      {!wide && (
        <MobileTabs
          view={view}
          onView={setView}
          agentOpen={agentOpen}
          onToggleAgent={() => setAgentOpen((v) => !v)}
        />
      )}
      {!agentOpen && <SelectionAsk selection={selection} clear={clearSelection} wide={wide} asks={asks} />}
      <UnsavedChangesGuard when={dirty} />
    </Desk>
  );
}
