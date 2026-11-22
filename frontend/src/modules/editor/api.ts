/** Document content API (spec 13). Wire mapping lives here. */
import type { Schemas } from "@/api/models";
import { apiClient } from "@/lib/api-client";

import type { DocumentContent } from "./types";

type DocumentWire = Schemas["DocumentContentRead"];

export async function getDocument(projectId: string, docId: string): Promise<DocumentContent> {
  const wire = await apiClient.get<DocumentWire>(`/api/v1/projects/${projectId}/documents/${docId}`);
  return { id: wire.entity_id, content: wire.content, version: wire.version };
}
