/** The project chat in the editor: its button in the bar and its view in the agent window (spec 117). */
import { useState } from "react";

import { config } from "@/config";
import type { AgentSide, SideView } from "@/modules/agent";
import { ChatButton, ChatPanel, useChatUnread } from "@/modules/discussion";

export function useWorkspaceChat(
  projectId: string,
  agentOpen: boolean,
  setAgentOpen: (open: boolean) => void,
) {
  const [sideView, setSideView] = useState<SideView>("agent");
  const chatVisible = agentOpen && sideView === "chat";
  const unread = useChatUnread(projectId);
  const openChat = () => {
    setSideView("chat");
    setAgentOpen(true);
  };
  const button = config.agentEnabled ? <ChatButton unread={unread.count} onOpen={openChat} /> : undefined;
  const side: AgentSide = {
    view: sideView,
    onViewChange: setSideView,
    chat: <ChatPanel projectId={projectId} active={chatVisible} />,
  };
  return { button, side };
}
