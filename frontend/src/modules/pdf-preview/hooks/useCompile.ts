/**
 * Compile trigger + live-status state machine (spec 24, §5.3.3).
 *
 * idle → (Compile) → queued → running → success | failure | timeout |
 * cancelled | error. Live status comes from `useCompileStream`.
 */
import { useCallback, useReducer, useRef } from "react";

import i18n from "@/i18n/config";

import { cancelCompile, requestCompile } from "../api";
import { type CompileState, type CompileStatus, isActive, isTerminal } from "../types";
import { useCompileStream } from "./useCompileStream";

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
              (s.status === "error" ? i18n.t("preview:announce.error") : i18n.t("preview:announce.failed")))
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

  const activeRef = useRef(false); // a compile is in flight (guards re-entry)

  const onSnapshot = useCallback((snapshot: CompileStatus) => dispatch({ type: "snapshot", snapshot }), []);
  const { handleSnapshot, subscribe } = useCompileStream(projectId, activeRef, onSnapshot);

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
