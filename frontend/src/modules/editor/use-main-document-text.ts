import { useQuery } from "@tanstack/react-query";

import { getDocument } from "./api";
import { documentKey } from "./use-document";

/**
 * The text of the project's main document, for the packages it loads (spec 114). The saved text is what is read,
 * so an edit not yet saved is not seen. Undefined until it loads.
 */
export function useMainDocumentText(
  projectId: string,
  rootDocId: string | null | undefined,
): string | undefined {
  const query = useQuery({
    queryKey: documentKey(projectId, rootDocId ?? ""),
    queryFn: () => getDocument(projectId, rootDocId!),
    enabled: Boolean(rootDocId),
  });
  return query.data?.content;
}
