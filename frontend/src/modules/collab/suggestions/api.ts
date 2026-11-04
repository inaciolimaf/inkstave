/** The caller's Suggesting preference in a project (spec 119). The wire shapes come from the generated types. */
import { apiClient } from "@/lib/api-client";

export function setSuggestMode(projectId: string, suggestMode: boolean): Promise<{ suggest_mode: boolean }> {
  return apiClient.patch<{ suggest_mode: boolean }>(`/api/v1/projects/${projectId}/me`, {
    suggest_mode: suggestMode,
  });
}
