import { useCallback, useEffect, useRef, useState, type RefObject } from "react";

import { saveDocument } from "../api";
import type { DocumentContent } from "../types";
import type { AutosaveState } from "./types";
import { useAutosaveFlush } from "./use-autosave-flush";

const EMPTY: AutosaveState = {
  documentId: null,
  baseVersion: 0,
  serverText: "",
  localText: "",
  displayText: "",
  status: "clean",
  lastSavedAt: null,
  retryCount: 0,
  conflict: null,
};

export interface DocumentAutosave {
  status: AutosaveState["status"];
  displayText: string;
  lastSavedAt: number | null;
  hasUnsaved: boolean;
  conflict: AutosaveState["conflict"];
  onLocalChange: (text: string) => void;
  saveNow: () => void;
  resolveReload: () => void;
  resolveKeepMine: () => void;
}

function useConflictResolution(
  stateRef: RefObject<AutosaveState>,
  patch: (p: Partial<AutosaveState>) => void,
  flush: () => Promise<void>,
) {
  const resolveReload = useCallback(() => {
    const s = stateRef.current;
    if (!s.conflict) return;
    patch({
      displayText: s.conflict.currentContent,
      localText: s.conflict.currentContent,
      serverText: s.conflict.currentContent,
      baseVersion: s.conflict.currentVersion,
      status: "clean",
      conflict: null,
      lastSavedAt: Date.now(),
    });
  }, [stateRef, patch]);

  const resolveKeepMine = useCallback(() => {
    const s = stateRef.current;
    if (!s.conflict) return;
    // Rebase onto the new server version, then re-save our local text.
    patch({
      baseVersion: s.conflict.currentVersion,
      serverText: s.conflict.currentContent,
      status: "dirty",
      conflict: null,
    });
    window.setTimeout(() => void flush(), 0);
  }, [stateRef, patch, flush]);

  return { resolveReload, resolveKeepMine };
}

function useFlushTriggers(stateRef: RefObject<AutosaveState>, flush: () => Promise<void>) {
  // Flush on tab hide; auto-save on reconnect.
  useEffect(() => {
    const onVisibility = () => {
      if (document.visibilityState === "hidden") void flush();
    };
    const onOnline = () => {
      const status = stateRef.current.status;
      if (status === "offline" || status === "error" || status === "dirty") void flush();
    };
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("online", onOnline);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("online", onOnline);
    };
  }, [stateRef, flush]);
}

export function useDocumentAutosave(projectId: string, loaded: DocumentContent | null): DocumentAutosave {
  const [state, setState] = useState<AutosaveState>(EMPTY);
  const stateRef = useRef(state);
  stateRef.current = state;

  const patch = useCallback((p: Partial<AutosaveState>) => setState((s) => ({ ...s, ...p })), []);

  const { flush, scheduleDebounce, clearTimers } = useAutosaveFlush(projectId, stateRef, patch);
  const { resolveReload, resolveKeepMine } = useConflictResolution(stateRef, patch, flush);

  const onLocalChange = useCallback(
    (text: string) => {
      const s = stateRef.current;
      if (text === s.localText) return;
      const status = s.status === "conflict" ? "conflict" : text === s.serverText ? "clean" : "dirty";
      patch({ localText: text, status });
      if (status === "dirty") scheduleDebounce();
    },
    [patch, scheduleDebounce],
  );

  // Seed on document switch; flush the outgoing doc on the way out.
  useEffect(() => {
    if (!loaded) return;
    setState({
      documentId: loaded.id,
      baseVersion: loaded.version,
      serverText: loaded.content,
      localText: loaded.content,
      displayText: loaded.content,
      status: "clean",
      lastSavedAt: null,
      retryCount: 0,
      conflict: null,
    });
    return () => {
      const s = stateRef.current;
      if (s.documentId && s.localText !== s.serverText && s.status !== "conflict") {
        void saveDocument(projectId, s.documentId, s.localText, s.baseVersion).catch(() => {});
      }
      clearTimers();
    };
    // Runs once per document: a refetch of the same id must not reset unsaved local text.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loaded?.id]);

  useFlushTriggers(stateRef, flush);

  return {
    status: state.status,
    displayText: state.displayText,
    lastSavedAt: state.lastSavedAt,
    hasUnsaved: state.status !== "clean",
    conflict: state.conflict,
    onLocalChange,
    saveNow: flush,
    resolveReload,
    resolveKeepMine,
  };
}
