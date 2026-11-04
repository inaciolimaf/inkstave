import { config } from "@/config";
import { AgentPanel } from "@/modules/agent";
import type { AgentRequest, AgentSide } from "@/modules/agent";
import type { DocumentBridge } from "@/modules/diff-review";
import type { TreeEntity } from "@/modules/file-tree";
import { HistoryPanel } from "@/modules/history";

/** The panels that open over the workspace. */
export function WorkspaceDrawers({
  projectId,
  openDoc,
  agentOpen,
  onAgentOpenChange,
  agentRequest,
  documentBridge,
  onBeforeSend,
  historyOpen,
  onHistoryOpenChange,
  side,
}: {
  projectId: string;
  openDoc: TreeEntity | null;
  agentOpen: boolean;
  onAgentOpenChange: (open: boolean) => void;
  agentRequest: AgentRequest | null;
  documentBridge: DocumentBridge | undefined;
  onBeforeSend: () => Promise<void>;
  historyOpen: boolean;
  onHistoryOpenChange: (open: boolean) => void;
  /** The project chat that shares the agent window (spec 117). */
  side: AgentSide;
}) {
  return (
    <>
      {config.agentEnabled && (
        <AgentPanel
          projectId={projectId}
          open={agentOpen}
          onOpenChange={onAgentOpenChange}
          request={agentRequest}
          documentBridge={documentBridge}
          onBeforeSend={onBeforeSend}
          onReviewProposal={() => {
            // The diff-review surface (spec 47) opens inside the panel via documentBridge.
          }}
          side={side}
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
