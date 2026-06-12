/** Diff-review state: load proposal, decisions, drift, preview, apply (spec 47). */
import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState } from "react";

import { fetchProposal } from "./api";
import { blockedAgainst, rebaseHunks } from "./hunks";
import type { ApplyFileResult, ApplyPhase, DocumentBridge, FileReviewState } from "./types";

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

  const [decisions, setDecisions] = useState<Record<string, Record<string, boolean>>>({});
  const [files, setFiles] = useState<Record<string, FileReviewState>>({});
  const [liveContent, setLiveContent] = useState<Record<string, string>>({});
  const [applyPhase, setApplyPhase] = useState<ApplyPhase>("idle");
  const [results, setResults] = useState<ApplyFileResult[] | null>(null);

  // On (re)load, default every hunk to accepted and evaluate drift against live content.
  useEffect(() => {
    if (!proposal) return;
    let cancelled = false;
    void (async () => {
      const nextDecisions: Record<string, Record<string, boolean>> = {};
      const nextFiles: Record<string, FileReviewState> = {};
      const nextLive: Record<string, string> = {};
      for (const file of proposal.files) {
        nextDecisions[file.path] = Object.fromEntries(file.hunks.map((h) => [h.id, true]));
        const live = (await bridge.readContent(file.path)) ?? "";
        const blocked = blockedAgainst(live, file.hunks);
        nextLive[file.path] = live;
        nextFiles[file.path] = {
          path: file.path,
          baseVersion: file.baseVersion,
          decisions: nextDecisions[file.path],
          baseChanged: blocked.length > 0,
          blockedHunkIds: blocked,
        };
      }
      if (!cancelled) {
        setDecisions(nextDecisions);
        setFiles(nextFiles);
        setLiveContent(nextLive);
        setApplyPhase("idle");
        setResults(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [proposal, bridge]);

  const acceptedSet = useCallback(
    (path: string) =>
      new Set(
        Object.entries(decisions[path] ?? {})
          .filter(([, v]) => v)
          .map(([k]) => k),
      ),
    [decisions],
  );

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
      return rebaseHunks(liveContent[path] ?? "", file.hunks, acceptedSet(path)).target;
    },
    [proposal, liveContent, acceptedSet],
  );

  const counts = useMemo(() => {
    let accepted = 0;
    let total = 0;
    for (const file of proposal?.files ?? []) {
      total += file.hunks.length;
      accepted += file.hunks.filter((h) => decisions[file.path]?.[h.id]).length;
    }
    return { accepted, total };
  }, [proposal, decisions]);

  // What a confirmed apply would do (applicable accepted hunks vs blocked).
  const plan = useMemo(() => {
    let applicable = 0;
    let blocked = 0;
    let fileCount = 0;
    for (const file of proposal?.files ?? []) {
      const accepted = new Set(
        file.hunks.filter((h) => decisions[file.path]?.[h.id]).map((h) => h.id),
      );
      const r = rebaseHunks(liveContent[file.path] ?? "", file.hunks, accepted);
      if (r.appliedHunkIds.length > 0) fileCount += 1;
      applicable += r.appliedHunkIds.length;
      blocked += r.blockedHunkIds.length;
    }
    return { fileCount, applicable, blocked };
  }, [proposal, decisions, liveContent]);

  const apply = useCallback(async (): Promise<{
    phase: ApplyPhase;
    results: ApplyFileResult[];
  }> => {
    if (!proposal) return { phase: "idle", results: [] };
    setApplyPhase("applying");
    const out: ApplyFileResult[] = [];
    for (const file of proposal.files) {
      const accepted = new Set(
        file.hunks.filter((h) => decisions[file.path]?.[h.id]).map((h) => h.id),
      );
      try {
        const live = (await bridge.readContent(file.path)) ?? "";
        const r = rebaseHunks(live, file.hunks, accepted);
        if (r.appliedHunkIds.length > 0) await bridge.applyContent(file.path, r.target);
        out.push({
          path: file.path,
          appliedHunks: r.appliedHunkIds,
          blockedHunks: r.blockedHunkIds,
        });
      } catch (err) {
        out.push({ path: file.path, appliedHunks: [], blockedHunks: [], error: String(err) });
      }
    }
    const phase: ApplyPhase = out.some((r) => r.error) ? "error" : "applied";
    setResults(out);
    setApplyPhase(phase);
    return { phase, results: out };
  }, [proposal, decisions, bridge]);

  return {
    proposal,
    loading: query.isLoading,
    isError: query.isError,
    refetch: query.refetch,
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
