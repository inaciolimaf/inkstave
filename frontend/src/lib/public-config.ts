import { useQuery } from "@tanstack/react-query";

import { apiClient } from "@/lib/api-client";

/** Optional features this server runs (`GET /api/v1/config`, spec 121). Read once per session. */
export interface PublicConfig {
  git_enabled: boolean;
}

const OFF: PublicConfig = { git_enabled: false };

/** The server's public configuration. Until it arrives, every optional feature reads as off. */
export function usePublicConfig(): PublicConfig {
  const { data } = useQuery({
    queryKey: ["public-config"],
    queryFn: () => apiClient.get<PublicConfig>("/api/v1/config", { auth: false }),
    staleTime: Number.POSITIVE_INFINITY,
  });
  return data ?? OFF;
}
