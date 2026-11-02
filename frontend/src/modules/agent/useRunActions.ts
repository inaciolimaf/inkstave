/** What the user does to a run: send, stop and retry (spec 46). */
import { useCallback, useRef, type Dispatch, type SetStateAction } from "react";

import i18n from "@/i18n/config";
import { ApiError } from "@/lib/api-client";
import { formatNumber } from "@/lib/formatting";

import { startRun, stopRun } from "./api";
import { applyEvent } from "./reducer";
import type { AgentEvent, AgentRunState } from "./types";

const TOO_LONG = "message_too_long";

function tooLongEvent(err: ApiError): AgentEvent {
  const limit = (err.details?.[0] as { max_chars?: number } | undefined)?.max_chars ?? 0;
  const message = i18n.t("agent:error.messages.message_too_long", {
    limit: formatNumber(limit),
  });
  return { type: "error", code: TOO_LONG, message };
}

/** The server's reason for refusing a run; only a 5xx or a network failure is ours to hide. */
function startFailure(err: unknown): AgentEvent {
  if (err instanceof ApiError && err.type === TOO_LONG) return tooLongEvent(err);
  if (err instanceof ApiError && err.status < 500 && err.type) {
    return { type: "error", code: err.type, message: err.detail };
  }
  return { type: "error", code: "internal", message: "" };
}

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
    /** Resolves to false when the server refuses the text itself, so the caller can restore the draft. */
    async (text: string): Promise<boolean> => {
      const content = text.trim();
      if (!content || run.phase === "starting" || run.phase === "streaming") return true;
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
        return true;
      } catch (err) {
        const event = startFailure(err);
        const refused = event.code === TOO_LONG;
        setRun((prev) => {
          const items = refused ? prev.items.filter((item) => item.id !== userItem.id) : prev.items;
          return applyEvent({ ...prev, items }, event);
        });
        return !refused;
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
