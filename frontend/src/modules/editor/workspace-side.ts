/** The panels that share the side of the editor: the agent window with its chat view, and the dialogs (specs 117, 118). */
import { useAgentOpen } from "./use-agent-open";
import { useWorkspaceChat } from "./workspace-chat";
import { useWorkspaceDialogs } from "./workspace-hooks";

export function useWorkspaceSide(projectId: string) {
  const dialogs = useWorkspaceDialogs();
  const [agentOpen, setAgentOpen] = useAgentOpen(projectId);
  const chat = useWorkspaceChat(projectId, agentOpen, setAgentOpen);
  return { dialogs, agentOpen, setAgentOpen, chat };
}
