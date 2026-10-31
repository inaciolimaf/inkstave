import { useEffect, useState } from "react";

/** Whether the agent panel is open, remembered per project. */
export function useAgentOpen(projectId: string) {
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
  return [agentOpen, setAgentOpen] as const;
}
