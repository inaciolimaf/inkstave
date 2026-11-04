/** Role ordering for share links (spec 116): a link never lowers a role. */
import type { LinkRole, Role } from "./types";

const RANK: Record<Role, number> = { viewer: 1, editor: 2, owner: 3 };

/** True when the caller's current role already covers what the link grants. */
export function alreadyHasAccess(current: Role | null, linkRole: LinkRole): boolean {
  return current !== null && RANK[current] >= RANK[linkRole];
}
