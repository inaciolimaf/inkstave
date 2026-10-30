/**
 * Fetch parsed problems for a compile (spec 27). Re-fetches whenever the compile
 * key changes — each compile has a fresh id, so a recompile refreshes naturally.
 */
import { useEffect, useState } from "react";

import { type CompileProblems, type ProblemsReason, getProblems } from "../problems";

export interface ProblemsState {
  problems: CompileProblems | null;
  reason: ProblemsReason | null;
  loading: boolean;
}

const EMPTY: ProblemsState = { problems: null, reason: null, loading: false };

export function useProblems(projectId: string, compileKey: string | null): ProblemsState {
  const [state, setState] = useState<ProblemsState>(EMPTY);

  useEffect(() => {
    if (!compileKey) {
      setState(EMPTY);
      return;
    }
    let cancelled = false;
    setState((s) => ({ ...s, loading: true }));
    getProblems(projectId, compileKey).then((result) => {
      if (cancelled) return;
      if (result.ok) setState({ problems: result.value, reason: null, loading: false });
      else setState({ problems: null, reason: result.reason, loading: false });
    });
    return () => {
      cancelled = true;
    };
  }, [projectId, compileKey]);

  return state;
}
