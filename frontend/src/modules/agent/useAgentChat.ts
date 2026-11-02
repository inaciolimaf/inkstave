/** Orchestrates agent sessions, runs, and the live SSE stream (spec 46). */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";

import { createSession, getSession, listSessions } from "./api";
import { historyToItems, initialRunState } from "./reducer";
import type { AgentRunState } from "./types";
import { useRunActions } from "./useRunActions";
import { useRunStream } from "./useRunStream";

export function useAgentChat(projectId: string, onBeforeSend?: () => Promise<void>) {
  const qc = useQueryClient();
  const sessionsQuery = useQuery({
    queryKey: ["agent-sessions", projectId],
    queryFn: () => listSessions(projectId),
  });

  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [run, setRun] = useState<AgentRunState>(initialRunState());
  const [transcriptLoading, setTranscriptLoading] = useState(false);
  const { openStream, closeStream } = useRunStream(projectId, setRun);

  const createActiveSession = useCallback(async () => {
    const session = await createSession(projectId);
    await qc.invalidateQueries({ queryKey: ["agent-sessions", projectId] });
    setActiveSessionId(session.id);
    setRun(initialRunState(session.id));
    return session.id;
  }, [qc, projectId]);

  const { send, stop, retry } = useRunActions({
    projectId,
    run,
    setRun,
    activeSessionId,
    createActiveSession,
    openStream,
    onBeforeSend,
  });

  const loadTranscript = useCallback(
    async (sessionId: string) => {
      setTranscriptLoading(true);
      try {
        const detail = await getSession(projectId, sessionId);
        setRun({
          sessionId,
          runId: null,
          phase: "idle",
          items: historyToItems(detail.messages, detail.diffs, detail.file_ops),
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
    await createActiveSession();
  }, [closeStream, createActiveSession]);

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
