/**
 * Follows one compile's live status: the spec-22 SSE stream, with a polling
 * fallback when `EventSource` is unavailable or errors. Everything stops at a
 * terminal status and on unmount.
 */
import { type RefObject, useCallback, useEffect, useRef } from "react";

import { config } from "@/config";

import { compileEventsUrl, getCompile } from "../api";
import { type CompileStatus, isTerminal } from "../types";

export function useCompileStream(
  projectId: string,
  /** True while a compile is in flight; cleared here at a terminal status. */
  activeRef: RefObject<boolean>,
  onSnapshot: (snapshot: CompileStatus) => void,
) {
  const esRef = useRef<EventSource | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopWatching = useCallback(() => {
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
    if (pollRef.current !== null) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const handleSnapshot = useCallback(
    (snapshot: CompileStatus) => {
      onSnapshot(snapshot);
      if (isTerminal(snapshot.status)) {
        activeRef.current = false;
        stopWatching();
      }
    },
    [activeRef, onSnapshot, stopWatching],
  );

  const startPolling = useCallback(
    (compileId: string) => {
      if (pollRef.current !== null) return;
      pollRef.current = setInterval(() => {
        getCompile(projectId, compileId)
          .then(handleSnapshot)
          .catch(() => {});
      }, config.compilePollIntervalMs);
    },
    [projectId, handleSnapshot],
  );

  const subscribe = useCallback(
    (compileId: string) => {
      if (typeof EventSource === "undefined") {
        startPolling(compileId);
        return;
      }
      let es: EventSource;
      try {
        es = new EventSource(compileEventsUrl(projectId, compileId));
      } catch {
        startPolling(compileId);
        return;
      }
      esRef.current = es;
      es.addEventListener("status", (event) => {
        try {
          handleSnapshot(JSON.parse((event as MessageEvent).data) as CompileStatus);
        } catch {
          /* ignore malformed frames */
        }
      });
      es.onerror = () => {
        // SSE failed or closed before a terminal status: fall back to polling.
        es.close();
        if (esRef.current === es) esRef.current = null;
        if (activeRef.current) startPolling(compileId);
      };
    },
    [projectId, activeRef, handleSnapshot, startPolling],
  );

  // Clean up any open stream/poll on unmount.
  useEffect(() => stopWatching, [stopWatching]);

  return { handleSnapshot, subscribe };
}
