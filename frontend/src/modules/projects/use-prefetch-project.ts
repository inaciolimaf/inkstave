import { useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";

import { loadEditorRoute } from "@/lib/route-chunks";

import { getProject } from "./api";
import { projectKey } from "./project-key";

const PREFETCH_FRESH_MS = 30_000;

/** Warms the editor when a pointer or focus lands on a project, the obvious next step. */
export function usePrefetchProject() {
  const queryClient = useQueryClient();
  return useCallback(
    (projectId: string) => {
      void loadEditorRoute();
      void queryClient.prefetchQuery({
        queryKey: projectKey(projectId),
        queryFn: () => getProject(projectId),
        staleTime: PREFETCH_FRESH_MS,
      });
    },
    [queryClient],
  );
}
