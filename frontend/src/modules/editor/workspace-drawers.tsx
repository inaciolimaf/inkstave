import { config } from "@/config";
import { AgentPanel } from "@/modules/agent";
import type { AgentRequest, AgentSide } from "@/modules/agent";
import type { ProposalRef } from "@/modules/diff-review";
import type { TreeEntity } from "@/modules/file-tree";
import { HistoryPanel } from "@/modules/history";

/** The panels that open over the workspace. */
export function WorkspaceDrawers({
  projectId,
  openDoc,
  agentOpen,
  onAgentOpenChange,
  agentRequest,
  proposals,
  onBeforeSend,
  dialogs,
  side,
}: {
  projectId: string;
  openDoc: TreeEntity | null;
  agentOpen: boolean;
  onAgentOpenChange: (open: boolean) => void;
  agentRequest: AgentRequest | null;
  /** The inline review of the agent's proposals (spec 110). */
  proposals: { proposalStatuses: Record<string, string>; open: (ref: ProposalRef) => void };
  onBeforeSend: () => Promise<void>;
  dialogs: { historyOpen: boolean; setHistoryOpen: (open: boolean) => void };
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
          proposalStatuses={proposals.proposalStatuses}
          onBeforeSend={onBeforeSend}
          onReviewProposal={proposals.open}
          side={side}
        />
      )}
      {openDoc?.type === "doc" && (
        <HistoryPanel
          projectId={projectId}
          docId={openDoc.id}
          open={dialogs.historyOpen}
          onOpenChange={dialogs.setHistoryOpen}
        />
      )}
    </>
  );
}
