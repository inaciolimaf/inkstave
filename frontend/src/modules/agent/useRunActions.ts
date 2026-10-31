/** What the user does to a run: send, stop and retry (spec 46). */
import { useCallback, useRef, type Dispatch, type SetStateAction } from "react";

import i18n from "@/i18n/config";

import { startRun, stopRun } from "./api";
import { applyEvent } from "./reducer";
import type { AgentRunState } from "./types";

export function useRunActions({
  projectId,
  run,
  setRun,
  activeSessionId,
  createActiveSession,
  openStream,
  onBeforeSend,
}: {
  projectId: string;
  run: AgentRunState;
  setRun: Dispatch<SetStateAction<AgentRunState>>;
  activeSessionId: string | null;
  createActiveSession: () => Promise<string>;
  openStream: (sessionId: string, runId: string) => void;
  onBeforeSend?: () => Promise<void>;
}) {
  const lastInstruction = useRef<string>("");

  const send = useCallback(
    async (text: string) => {
      const content = text.trim();
      if (!content || run.phase === "starting" || run.phase === "streaming") return;
      lastInstruction.current = content;

      const sessionId = activeSessionId ?? (await createActiveSession());

      const userItem = {
        kind: "message" as const,
        id: `u-${Date.now()}`,
        role: "user" as const,
        text: content,
        status: "complete" as const,
      };
      setRun((prev) => ({
        ...prev,
        sessionId,
        phase: "starting",
        error: undefined,
        items: [...prev.items, userItem],
      }));

      try {
        // Push pending local edits to the server CRDT room first, so the backend
        // can materialise current text before the worker reads it (best-effort).
        await onBeforeSend?.().catch(() => undefined);
        const { runId } = await startRun(projectId, sessionId, content);
        setRun((prev) => ({ ...prev, runId, phase: "streaming" }));
        openStream(sessionId, runId);
      } catch {
        setRun((prev) =>
          applyEvent(prev, {
            type: "error",
            code: "internal",
            message: i18n.t("agent:error.messages.startFailed"),
          }),
        );
      }
    },
    [activeSessionId, projectId, run.phase, setRun, createActiveSession, openStream, onBeforeSend],
  );

  const stop = useCallback(async () => {
    if (!run.runId || !run.sessionId) return;
    setRun((prev) => ({ ...prev, phase: "stopping" }));
    try {
      await stopRun(projectId, run.sessionId, run.runId);
    } catch {
      // The cancel/terminal event (or transport error) will settle the phase.
    }
  }, [projectId, run.runId, run.sessionId, setRun]);

  const retry = useCallback(() => {
    if (lastInstruction.current) void send(lastInstruction.current);
  }, [send]);

  return { send, stop, retry };
}
