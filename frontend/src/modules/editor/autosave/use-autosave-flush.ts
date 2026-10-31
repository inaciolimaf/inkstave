import { useCallback, useRef, type RefObject } from "react";

import { saveDocument, VersionConflictError } from "../api";
import { DEBOUNCE_MS, MAX_RETRIES, RETRY_BACKOFF_MS, type AutosaveState } from "./types";

/** The single-flight save, with its debounce and its capped retry. */
export function useAutosaveFlush(
  projectId: string,
  stateRef: RefObject<AutosaveState>,
  patch: (p: Partial<AutosaveState>) => void,
) {
  const savingRef = useRef(false);
  const debounceRef = useRef<number | null>(null);
  const retryRef = useRef<number | null>(null);

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
  }, [projectId, stateRef, patch]);

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

  const clearTimers = useCallback(() => {
    if (debounceRef.current !== null) clearTimeout(debounceRef.current);
    if (retryRef.current !== null) clearTimeout(retryRef.current);
  }, []);

  return { flush, scheduleDebounce, clearTimers };
}
