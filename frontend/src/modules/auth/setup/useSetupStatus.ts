/** Query for first-run setup status (spec 63). Cached for the session. */
import { useQuery } from "@tanstack/react-query";

import { getSetupStatus } from "./api";

export function useSetupStatus() {
  return useQuery({
    queryKey: ["setup-status"],
    queryFn: getSetupStatus,
    staleTime: Infinity,
  });
}
