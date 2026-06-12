/** The caller's role + capabilities on a project, for capability-gated UI (spec 34). */
import { useQuery } from "@tanstack/react-query";

import { getPermissions, type Permissions } from "./api";

export function usePermissions(projectId: string) {
  return useQuery({
    queryKey: ["permissions", projectId],
    queryFn: () => getPermissions(projectId),
  });
}

export function hasCapability(perms: Permissions | undefined, cap: string): boolean {
  return perms?.capabilities.includes(cap) ?? false;
}

/** True only once permissions are known to be the read-only `viewer` role. */
export function isReadOnly(perms: Permissions | undefined): boolean {
  return perms?.role === "viewer";
}
