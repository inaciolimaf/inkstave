/** Orchestrates agent sessions, runs, and the live SSE stream (spec 46). */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";

import i18n from "@/i18n/config";

import { createSession, getSession, listSessions, runEventsUrl, startRun, stopRun } from "./api";
import { applyEvent, historyToItems, initialRunState } from "./reducer";
import type { AgentEvent, AgentRunState } from "./types";

const STREAM_EVENT_TYPES = ["token", "tool_call", "tool_result", "diff_proposed", "done", "error"];

export function useAgentChat(projectId: string, onBeforeSend?: () => Promise<void>) {
  const qc = useQueryClient();
  const sessionsQuery = useQuery({
    queryKey: ["agent-sessions", projectId],
    queryFn: () => listSessions(projectId),
  });

  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [run, setRun] = useState<AgentRunState>(initialRunState());
  const [transcriptLoading, setTranscriptLoading] = useState(false);
  const esRef = useRef<EventSource | null>(null);
  const lastInstruction = useRef<string>("");

  const closeStream = useCallback(() => {
    esRef.current?.close();
    esRef.current = null;
  }, []);

  useEffect(() => closeStream, [closeStream]);

  const invalidateSessions = useCallback(
    () => qc.invalidateQueries({ queryKey: ["agent-sessions", projectId] }),
    [qc, projectId],
  );

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
    [projectId, closeStream],
  );

  const loadTranscript = useCallback(
    async (sessionId: string) => {
      setTranscriptLoading(true);
      try {
        const detail = await getSession(projectId, sessionId);
        setRun({
          sessionId,
          runId: null,
          phase: "idle",
          items: historyToItems(detail.messages, detail.diffs),
          seenSeqs: [],
        });
      } finally {
        setTranscriptLoading(false);
      }
    },
    [projectId],
  );

  const selectSession = useCallback(
    async (sessionId: string) => {
      closeStream();
      setActiveSessionId(sessionId);
      await loadTranscript(sessionId);
    },
    [closeStream, loadTranscript],
  );

  const newChat = useCallback(async () => {
    closeStream();
    const session = await createSession(projectId);
    await invalidateSessions();
    setActiveSessionId(session.id);
    setRun(initialRunState(session.id));
  }, [closeStream, projectId, invalidateSessions]);

  const send = useCallback(
    async (text: string) => {
      const content = text.trim();
      if (!content || run.phase === "starting" || run.phase === "streaming") return;
      lastInstruction.current = content;

      let sessionId = activeSessionId;
      if (!sessionId) {
        const session = await createSession(projectId);
        await invalidateSessions();
        sessionId = session.id;
        setActiveSessionId(session.id);
        setRun(initialRunState(session.id));
      }

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
    [activeSessionId, projectId, run.phase, invalidateSessions, openStream, onBeforeSend],
  );

  const stop = useCallback(async () => {
    if (!run.runId || !run.sessionId) return;
    setRun((prev) => ({ ...prev, phase: "stopping" }));
    try {
      await stopRun(projectId, run.sessionId, run.runId);
    } catch {
      // The cancel/terminal event (or transport error) will settle the phase.
    }
  }, [projectId, run.runId, run.sessionId]);

  const retry = useCallback(() => {
    if (lastInstruction.current) void send(lastInstruction.current);
  }, [send]);

  return {
    sessions: sessionsQuery.data ?? [],
    activeSessionId,
    run,
    transcriptLoading,
    send,
    stop,
    retry,
    selectSession,
    newChat,
  };
}
