/**
 * Lazy-fetch + cache the raw compile log (spec 24, §5.3.6).
 *
 * The log is only fetched on demand — when the panel is expanded or a failure
 * auto-opens it — and cached per compile id so re-expanding does not refetch.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { getCompileLog } from "../api";

export interface CompileLogState {
  log: string | null;
  loading: boolean;
  error: string | null;
  fetchLog: () => void;
}

export function useCompileLog(projectId: string, compileId: string | null): CompileLogState {
  const [log, setLog] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fetchedFor = useRef<string | null>(null);

  // Reset the cache when the compile changes.
  useEffect(() => {
    fetchedFor.current = null;
    setLog(null);
    setError(null);
    setLoading(false);
  }, [compileId]);

  const fetchLog = useCallback(() => {
    if (!compileId || fetchedFor.current === compileId) return;
    fetchedFor.current = compileId;
    setLoading(true);
    setError(null);
    getCompileLog(projectId, compileId)
      .then((text) => setLog(text))
      .catch((err: unknown) => {
        fetchedFor.current = null; // allow a retry
        setError(err instanceof Error ? err.message : "Could not load the log.");
      })
      .finally(() => setLoading(false));
  }, [projectId, compileId]);

  return { log, loading, error, fetchLog };
}
