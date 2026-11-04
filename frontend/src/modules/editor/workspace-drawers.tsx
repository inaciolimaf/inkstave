import { config } from "@/config";
import { AgentPanel } from "@/modules/agent";
import type { AgentRequest } from "@/modules/agent";
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
  proposalStatuses,
  onReviewProposal,
  onBeforeSend,
  historyOpen,
  onHistoryOpenChange,
}: {
  projectId: string;
  openDoc: TreeEntity | null;
  agentOpen: boolean;
  onAgentOpenChange: (open: boolean) => void;
  agentRequest: AgentRequest | null;
  proposalStatuses: Record<string, string>;
  onReviewProposal: (ref: ProposalRef) => void;
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
          request={agentRequest}
          proposalStatuses={proposalStatuses}
          onBeforeSend={onBeforeSend}
          onReviewProposal={onReviewProposal}
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
