/** The text of one document, for the index. The document API is the one the editor reads (spec 13). */
import type { Schemas } from "@/api/models";
import { apiClient } from "@/lib/api-client";

export async function fetchDocumentText(projectId: string, docId: string): Promise<string> {
  const wire = await apiClient.get<Schemas["DocumentContentRead"]>(
    `/api/v1/projects/${projectId}/documents/${docId}`,
  );
  return wire.content;
}
