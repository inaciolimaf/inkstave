/** Git access token calls (spec 121). Thin wrappers over the apiClient. */

import { apiClient } from "@/lib/api-client";

export interface GitToken {
  id: string;
  name: string;
  prefix: string;
  created_at: string;
  last_used_at: string | null;
  expires_at: string | null;
}

/** The token itself appears only in the response to its creation. */
export interface GitTokenCreated extends GitToken {
  token: string;
}

export function listGitTokens(): Promise<{ tokens: GitToken[] }> {
  return apiClient.get<{ tokens: GitToken[] }>("/api/v1/git/tokens");
}

export function createGitToken(body: { name: string; expires_at?: string | null }): Promise<GitTokenCreated> {
  return apiClient.post<GitTokenCreated>("/api/v1/git/tokens", body);
}

export function revokeGitToken(tokenId: string): Promise<void> {
  return apiClient.delete<void>(`/api/v1/git/tokens/${tokenId}`);
}
