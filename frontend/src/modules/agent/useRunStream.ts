/** The live SSE connection of one agent run (spec 46). */
import { useCallback, useEffect, useRef, type Dispatch, type SetStateAction } from "react";

import i18n from "@/i18n/config";

import { runEventsUrl } from "./api";
import { applyEvent } from "./reducer";
import type { AgentEvent, AgentRunState } from "./types";

const STREAM_EVENT_TYPES = [
  "token",
  "tool_call",
  "tool_result",
  "diff_proposed",
  "file_op_proposed",
  "done",
  "error",
];

export function useRunStream(projectId: string, setRun: Dispatch<SetStateAction<AgentRunState>>) {
  const esRef = useRef<EventSource | null>(null);

  const closeStream = useCallback(() => {
    esRef.current?.close();
    esRef.current = null;
  }, []);

  useEffect(() => closeStream, [closeStream]);

  const openStream = useCallback(
    (sessionId: string, runId: string) => {
      closeStream();
      const es = new EventSource(runEventsUrl(projectId, sessionId, runId));
      esRef.current = es;
      const handle = (e: MessageEvent) => {
        let event: AgentEvent;
        try {
          event = JSON.parse(e.data);
        } catch {
          return;
        }
        setRun((prev) => applyEvent(prev, event));
        if (event.type === "done" || event.type === "error") closeStream();
      };
      for (const type of STREAM_EVENT_TYPES) {
        es.addEventListener(type, handle as EventListener);
      }
      es.onerror = () => {
        setRun((prev) =>
          ["starting", "streaming", "stopping"].includes(prev.phase)
            ? applyEvent(prev, {
                type: "error",
                code: "transport",
                message: i18n.t("agent:error.messages.connectionLost"),
              })
            : prev,
        );
        closeStream();
      };
    },
    [projectId, closeStream, setRun],
  );

  return { openStream, closeStream };
}
