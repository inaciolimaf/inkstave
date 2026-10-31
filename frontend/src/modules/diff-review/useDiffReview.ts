/** Diff-review state: load proposal, decisions, drift, preview, apply (spec 47). */
import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState } from "react";

import { fetchProposal } from "./api";
import { rebaseHunks } from "./hunks";
import { applyProposal, countHunks, loadReview, planApply, type Decisions } from "./review-state";
import type { ApplyFileResult, ApplyPhase, DocumentBridge, FileReviewState } from "./types";

export type DiffReview = ReturnType<typeof useDiffReview>;

export function useDiffReview(
  projectId: string,
  sessionId: string,
  proposalId: string | null,
  bridge: DocumentBridge,
  open: boolean,
) {
  const query = useQuery({
    queryKey: ["diff-proposal", projectId, sessionId, proposalId],
    queryFn: () => fetchProposal(projectId, sessionId, proposalId!),
    enabled: open && !!proposalId,
  });
  const proposal = query.data ?? null;

  const [decisions, setDecisions] = useState<Decisions>({});
  const [files, setFiles] = useState<Record<string, FileReviewState>>({});
  const [liveContent, setLiveContent] = useState<Record<string, string>>({});
  const [applyPhase, setApplyPhase] = useState<ApplyPhase>("idle");
  const [results, setResults] = useState<ApplyFileResult[] | null>(null);

  // On (re)load, default every hunk to accepted and evaluate drift against live content.
  useEffect(() => {
    if (!proposal) return;
    let cancelled = false;
    void loadReview(proposal, bridge).then((loaded) => {
      if (cancelled) return;
      setDecisions(loaded.decisions);
      setFiles(loaded.files);
      setLiveContent(loaded.liveContent);
      setApplyPhase("idle");
      setResults(null);
    });
    return () => {
      cancelled = true;
    };
  }, [proposal, bridge]);

  const toggleHunk = useCallback((path: string, hunkId: string) => {
    setDecisions((d) => ({ ...d, [path]: { ...d[path], [hunkId]: !d[path]?.[hunkId] } }));
  }, []);

  const setAll = useCallback(
    (path: string, accepted: boolean) => {
      const file = proposal?.files.find((f) => f.path === path);
      if (!file) return;
      setDecisions((d) => ({
        ...d,
        [path]: Object.fromEntries(file.hunks.map((h) => [h.id, accepted])),
      }));
    },
    [proposal],
  );

  const preview = useCallback(
    (path: string): string => {
      const file = proposal?.files.find((f) => f.path === path);
      if (!file) return "";
      const accepted = new Set(
        Object.entries(decisions[path] ?? {})
          .filter(([, v]) => v)
          .map(([k]) => k),
      );
      return rebaseHunks(liveContent[path] ?? "", file.hunks, accepted).target;
    },
    [proposal, liveContent, decisions],
  );

  const counts = useMemo(() => countHunks(proposal, decisions), [proposal, decisions]);
  const plan = useMemo(() => planApply(proposal, decisions, liveContent), [proposal, decisions, liveContent]);

  const apply = useCallback(async (): Promise<{ phase: ApplyPhase; results: ApplyFileResult[] }> => {
    if (!proposal) return { phase: "idle", results: [] };
    setApplyPhase("applying");
    const outcome = await applyProposal(proposal, decisions, bridge);
    setResults(outcome.results);
    setApplyPhase(outcome.phase);
    return outcome;
  }, [proposal, decisions, bridge]);

  return {
    proposal,
    // `data` is null, never undefined: a query that has not run shows "no changes", not an error.
    query: { data: proposal, isLoading: query.isLoading, isError: query.isError, refetch: query.refetch },
    files,
    decisions,
    counts,
    plan,
    applyPhase,
    setApplyPhase,
    results,
    toggleHunk,
    setAll,
    preview,
    apply,
  };
}
