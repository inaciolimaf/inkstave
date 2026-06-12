/** React Query hooks for the history feature (spec 38). */
import {
  type InfiniteData,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { toast } from "sonner";

import { createLabel, deleteLabel, getDiff, listVersions, restoreVersion } from "./api";
import type { VersionsPage } from "./types";

const PAGE_SIZE = 50;

export function versionsKey(projectId: string, docId: string) {
  return ["history-versions", projectId, docId] as const;
}

export function useVersions(projectId: string, docId: string, enabled: boolean) {
  return useInfiniteQuery({
    queryKey: versionsKey(projectId, docId),
    queryFn: ({ pageParam }) =>
      listVersions(projectId, docId, { before: pageParam ?? undefined, limit: PAGE_SIZE }),
    initialPageParam: null as number | null,
    getNextPageParam: (last) => (last.hasMore ? last.nextBefore : undefined),
    enabled,
  });
}

export function useDiff(
  projectId: string,
  docId: string,
  from: number | null,
  to: number | "current" | null,
) {
  return useQuery({
    queryKey: ["history-diff", projectId, docId, from, to],
    queryFn: () => getDiff(projectId, docId, from!, to!),
    enabled: from !== null && to !== null,
  });
}

export function useHistoryMutations(projectId: string, docId: string) {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: versionsKey(projectId, docId) });

  const versionsCacheKey = versionsKey(projectId, docId);

  const addLabel = useMutation({
    mutationFn: ({ version, name }: { version: number; name: string }) =>
      createLabel(projectId, docId, version, name),
    // Optimistically show the new badge before the server round-trip (§5.3.4, AC6).
    onMutate: async ({ version, name }: { version: number; name: string }) => {
      await qc.cancelQueries({ queryKey: versionsCacheKey });
      const previous = qc.getQueryData<InfiniteData<VersionsPage>>(versionsCacheKey);
      const tempId = `optimistic-${Date.now()}`;
      qc.setQueryData<InfiniteData<VersionsPage>>(versionsCacheKey, (data) => {
        if (!data) return data;
        return {
          ...data,
          pages: data.pages.map((page) => ({
            ...page,
            versions: page.versions.map((v) =>
              v.version === version ? { ...v, labels: [...v.labels, { id: tempId, name }] } : v,
            ),
          })),
        };
      });
      return { previous };
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) qc.setQueryData(versionsCacheKey, context.previous);
      toast.error("Couldn’t add the label.");
    },
    onSettled: invalidate,
  });

  const removeLabel = useMutation({
    mutationFn: (labelId: string) => deleteLabel(projectId, docId, labelId),
    onSuccess: invalidate,
  });

  const restore = useMutation({
    mutationFn: ({ version, labelName }: { version: number; labelName?: string }) =>
      restoreVersion(projectId, docId, version, labelName),
    onSuccess: invalidate,
  });

  return { addLabel, removeLabel, restore };
}
