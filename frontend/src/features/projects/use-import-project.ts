/** Import state machine: idle → uploading(progress) → processing → done | failed (spec 101). */
import { useCallback, useEffect, useRef, useState } from "react";

import {
  ImportUploadError,
  getImportStatus,
  importProjectZip,
  type ProjectImport,
} from "./api";

export type ImportPhase = "idle" | "uploading" | "processing" | "done" | "failed";

export interface ImportState {
  phase: ImportPhase;
  progress: number; // 0..1, meaningful during "uploading"
  projectId: string | null; // the new project (available once the upload returns 202)
  errorType: string | null; // machine code for i18n mapping
}

const POLL_INTERVAL_MS = 1000;
const TERMINAL = new Set(["success", "partial", "failure", "error"]);

const INITIAL: ImportState = { phase: "idle", progress: 0, projectId: null, errorType: null };

export function useImportProject(onSuccess: (projectId: string) => void) {
  const [state, setState] = useState<ImportState>(INITIAL);
  const cancelled = useRef(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const stopPolling = useCallback(() => {
    if (timer.current) {
      clearTimeout(timer.current);
      timer.current = null;
    }
  }, []);

  // Cancel any in-flight polling when the component unmounts.
  useEffect(() => {
    cancelled.current = false;
    return () => {
      cancelled.current = true;
      stopPolling();
    };
  }, [stopPolling]);

  const reset = useCallback(() => {
    stopPolling();
    setState(INITIAL);
  }, [stopPolling]);

  const poll = useCallback(
    (projectId: string, importId: string) => {
      const tick = async () => {
        if (cancelled.current) return;
        let row: ProjectImport;
        try {
          row = await getImportStatus(projectId, importId);
        } catch {
          // A transient read failure — keep polling.
          timer.current = setTimeout(() => void tick(), POLL_INTERVAL_MS);
          return;
        }
        if (cancelled.current) return;
        if (!TERMINAL.has(row.status)) {
          timer.current = setTimeout(() => void tick(), POLL_INTERVAL_MS);
          return;
        }
        if (row.status === "success" || row.status === "partial") {
          setState((s) => ({ ...s, phase: "done" }));
          onSuccess(projectId);
        } else {
          setState((s) => ({ ...s, phase: "failed", errorType: row.errorType ?? "generic" }));
        }
      };
      void tick();
    },
    [onSuccess],
  );

  const start = useCallback(
    async (file: File, name?: string) => {
      setState({ phase: "uploading", progress: 0, projectId: null, errorType: null });
      let row: ProjectImport;
      try {
        row = await importProjectZip(file, name, (fraction) => {
          if (!cancelled.current) setState((s) => ({ ...s, progress: fraction }));
        });
      } catch (err) {
        if (cancelled.current) return;
        const errorType =
          err instanceof ImportUploadError ? (err.errorType ?? "generic") : "generic";
        setState((s) => ({ ...s, phase: "failed", errorType }));
        return;
      }
      if (cancelled.current) return;
      setState({
        phase: "processing",
        progress: 1,
        projectId: row.projectId,
        errorType: null,
      });
      poll(row.projectId, row.importId);
    },
    [poll],
  );

  return { state, start, reset };
}
