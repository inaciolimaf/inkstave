/**
 * Compile trigger + live-status state machine (spec 24, §5.3.3).
 *
 * idle → (Compile) → queued → running → success | failure | timeout |
 * cancelled | error. Live status comes from the spec-22 SSE stream, with a
 * polling fallback when `EventSource` is unavailable or errors.
 */
import { useCallback, useEffect, useReducer, useRef } from "react";

import { config } from "@/config";
import i18n from "@/i18n/config";

import { cancelCompile, compileEventsUrl, getCompile, requestCompile } from "../api";
import { type CompileState, type CompileStatus, isActive, isTerminal } from "../types";

interface State {
  status: CompileState;
  compileId: string | null;
  /** Last compile that produced a viewable PDF; survives a later cancel. */
  lastSuccessId: string | null;
  meta: CompileStatus | null;
  error: string | null;
}

type Action =
  | { type: "start" }
  | { type: "snapshot"; snapshot: CompileStatus }
  | { type: "systemError"; message: string };

const INITIAL: State = {
  status: "idle",
  compileId: null,
  lastSuccessId: null,
  meta: null,
  error: null,
};

/** A concise, user-facing reason for a non-success terminal compile. */
function failureDetail(s: CompileStatus): string | null {
  if (s.error_message) return s.error_message;
  const log = s.log_excerpt;
  if (!log) return null;
  const lines = log
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);
  // LaTeX errors start with "! "; surface the first one, else the first line.
  return lines.find((l) => l.startsWith("!")) ?? lines[0] ?? null;
}

function reduce(state: State, action: Action): State {
  switch (action.type) {
    case "start":
      return { ...state, status: "queued", error: null };
    case "snapshot": {
      const s = action.snapshot;
      return {
        status: s.status,
        compileId: s.id,
        meta: s,
        lastSuccessId: s.status === "success" && s.has_pdf ? s.id : state.lastSuccessId,
        error:
          s.status === "error" || s.status === "failure" || s.status === "timeout"
            ? (failureDetail(s) ??
              (s.status === "error"
                ? i18n.t("preview:announce.error")
                : i18n.t("preview:announce.failed")))
            : null,
      };
    }
    case "systemError":
      return { ...state, status: "error", error: action.message };
  }
}

function progressLabelFor(status: CompileState): string {
  switch (status) {
    case "queued":
      return i18n.t("preview:compile.queued");
    case "running":
      return i18n.t("preview:compile.compiling");
    default:
      return i18n.t("preview:compile.working");
  }
}

export interface UseCompile {
  status: CompileState;
  compileId: string | null;
  lastSuccessId: string | null;
  meta: CompileStatus | null;
  progressLabel: string | null;
  error: string | null;
  compile: () => void;
  cancel: () => void;
}

export function useCompile(
  projectId: string,
  /** Flush pending local CRDT edits to the server before compiling (spec 31 §5.4). */
  flush?: () => Promise<void>,
): UseCompile {
  const [state, dispatch] = useReducer(reduce, INITIAL);

  const flushRef = useRef(flush);
  flushRef.current = flush;

  const esRef = useRef<EventSource | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const activeRef = useRef(false); // a compile is in flight (guards re-entry)

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
      dispatch({ type: "snapshot", snapshot });
      if (isTerminal(snapshot.status)) {
        activeRef.current = false;
        stopWatching();
      }
    },
    [stopWatching],
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
    [projectId, handleSnapshot, startPolling],
  );

  const compile = useCallback(() => {
    if (activeRef.current) return; // client-side debounce (§5.3.3)
    activeRef.current = true;
    dispatch({ type: "start" });
    // Drain pending local CRDT edits to the server so the compile sees them, then
    // request the compile. A flush failure must not strand the user, so proceed.
    Promise.resolve(flushRef.current?.())
      .catch(() => {})
      .then(() => requestCompile(projectId))
      .then((snapshot) => {
        if (!activeRef.current) return;
        handleSnapshot(snapshot);
        if (!isTerminal(snapshot.status)) subscribe(snapshot.id);
      })
      .catch((err: unknown) => {
        activeRef.current = false;
        dispatch({
          type: "systemError",
          message: err instanceof Error ? err.message : i18n.t("preview:errors.startCompile"),
        });
      });
  }, [projectId, handleSnapshot, subscribe]);

  const cancel = useCallback(() => {
    const id = state.compileId;
    if (!id || !activeRef.current) return;
    cancelCompile(projectId, id)
      .then(handleSnapshot)
      .catch(() => {});
  }, [projectId, state.compileId, handleSnapshot]);

  // Clean up any open stream/poll on unmount.
  useEffect(() => stopWatching, [stopWatching]);

  return {
    status: state.status,
    compileId: state.compileId,
    lastSuccessId: state.lastSuccessId,
    meta: state.meta,
    progressLabel: isActive(state.status) ? progressLabelFor(state.status) : null,
    error: state.error,
    compile,
    cancel,
  };
}
