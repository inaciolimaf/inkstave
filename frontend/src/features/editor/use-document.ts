import { useQuery } from "@tanstack/react-query";

import { getDocument } from "./api";

export function documentKey(projectId: string, docId: string) {
  return ["document", projectId, docId] as const;
}

export function useDocument(projectId: string, docId: string | null) {
  return useQuery({
    queryKey: documentKey(projectId, docId ?? ""),
    queryFn: () => getDocument(projectId, docId!),
    enabled: Boolean(docId),
  });
}
