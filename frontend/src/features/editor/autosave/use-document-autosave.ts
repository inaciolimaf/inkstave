import { useCallback, useEffect, useRef, useState } from "react";

import { saveDocument, VersionConflictError } from "../api";
import type { DocumentContent } from "../types";
import { DEBOUNCE_MS, MAX_RETRIES, RETRY_BACKOFF_MS, type AutosaveState } from "./types";

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

export function useDocumentAutosave(
  projectId: string,
  loaded: DocumentContent | null,
): DocumentAutosave {
  const [state, setState] = useState<AutosaveState>(EMPTY);
  const stateRef = useRef(state);
  stateRef.current = state;

  const savingRef = useRef(false);
  const debounceRef = useRef<number | null>(null);
  const retryRef = useRef<number | null>(null);

  const patch = useCallback((p: Partial<AutosaveState>) => setState((s) => ({ ...s, ...p })), []);

  const flush = useCallback(async () => {
    if (debounceRef.current !== null) {
      clearTimeout(debounceRef.current);
      debounceRef.current = null;
    }
    const s = stateRef.current;
    if (!s.documentId || s.status === "conflict") return;
    if (s.localText === s.serverText) {
      if (s.status !== "clean") patch({ status: "clean" });
      return;
    }
    if (savingRef.current) return; // single-flight; re-flushed after resolve

    savingRef.current = true;
    const attemptText = s.localText;
    const attemptVersion = s.baseVersion;
    const docId = s.documentId;
    patch({ status: "saving" });

    try {
      const { version } = await saveDocument(projectId, docId, attemptText, attemptVersion);
      savingRef.current = false;
      const stillDirty = stateRef.current.localText !== attemptText;
      patch({
        baseVersion: version,
        serverText: attemptText,
        lastSavedAt: Date.now(),
        retryCount: 0,
        status: stillDirty ? "dirty" : "clean",
      });
      if (stillDirty) {
        // Coalesced edits arrived during the save: re-flush on the next tick so
        // the advanced version/serverText above have committed first.
        if (debounceRef.current !== null) clearTimeout(debounceRef.current);
        debounceRef.current = window.setTimeout(() => {
          debounceRef.current = null;
          void flush();
        }, 0);
      }
    } catch (err) {
      savingRef.current = false;
      if (err instanceof VersionConflictError) {
        patch({ status: "conflict", conflict: err.conflict });
        return;
      }
      const retryCount = stateRef.current.retryCount + 1;
      if (retryCount > MAX_RETRIES) {
        patch({ status: "error", retryCount });
        return; // capped: stop auto-retrying, manual retry only
      }
      patch({ status: navigator.onLine ? "error" : "offline", retryCount });
      const delay = RETRY_BACKOFF_MS[Math.min(retryCount - 1, RETRY_BACKOFF_MS.length - 1)];
      if (retryRef.current !== null) clearTimeout(retryRef.current);
      retryRef.current = window.setTimeout(() => void flush(), delay);
    }
  }, [projectId, patch]);

  const scheduleDebounce = useCallback(
    (delay = DEBOUNCE_MS) => {
      if (debounceRef.current !== null) clearTimeout(debounceRef.current);
      debounceRef.current = window.setTimeout(() => {
        debounceRef.current = null;
        void flush();
      }, delay);
    },
    [flush],
  );

  const onLocalChange = useCallback(
    (text: string) => {
      const s = stateRef.current;
      if (text === s.localText) return;
      const status =
        s.status === "conflict" ? "conflict" : text === s.serverText ? "clean" : "dirty";
      patch({ localText: text, status });
      if (status === "dirty") scheduleDebounce();
    },
    [patch, scheduleDebounce],
  );

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
  }, [patch]);

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
  }, [patch, flush]);

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
      if (debounceRef.current !== null) clearTimeout(debounceRef.current);
      if (retryRef.current !== null) clearTimeout(retryRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loaded?.id]);

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
  }, [flush]);

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
