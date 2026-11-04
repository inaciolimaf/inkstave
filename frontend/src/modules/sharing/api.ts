/** Sharing API calls (spec 33). snake_case ↔ camelCase mapping lives here only. */
import type { Schemas } from "@/api/models";
import { apiClient } from "@/lib/api-client";

import type {
  AcceptResult,
  Invite,
  InviteCreated,
  InvitePreview,
  InviteRole,
  JoinResult,
  LinkRole,
  Member,
  Role,
  ShareLink,
  ShareLinkCreated,
  SharePreview,
} from "./types";

type MemberWire = Schemas["MemberRead"];

type InviteWire = Schemas["InviteRead"];

function toMember(w: MemberWire): Member {
  return {
    userId: w.user_id,
    name: w.name,
    email: w.email,
    role: w.role as Role,
    status: w.status,
    viaLink: w.via_link,
  };
}

function toShareLink(w: Schemas["ShareLinkRead"]): ShareLink {
  return { id: w.id, role: w.role as LinkRole, createdAt: w.created_at };
}

function toInvite(w: InviteWire): Invite {
  return {
    id: w.id,
    email: w.email,
    role: w.role as InviteRole,
    status: w.status,
    expiresAt: w.expires_at,
    createdAt: w.created_at,
  };
}

const base = (projectId: string) => `/api/v1/projects/${projectId}`;

export async function listMembers(projectId: string): Promise<Member[]> {
  return (await apiClient.get<MemberWire[]>(`${base(projectId)}/members`)).map(toMember);
}

export async function changeMemberRole(projectId: string, userId: string, role: InviteRole): Promise<Member> {
  return toMember(await apiClient.patch<MemberWire>(`${base(projectId)}/members/${userId}`, { role }));
}

export async function removeMember(projectId: string, userId: string): Promise<void> {
  await apiClient.delete(`${base(projectId)}/members/${userId}`);
}

export async function transferOwnership(projectId: string, toUserId: string): Promise<Member> {
  return toMember(
    await apiClient.post<MemberWire>(`${base(projectId)}/members/transfer`, {
      to_user_id: toUserId,
    }),
  );
}

export async function listInvites(projectId: string): Promise<Invite[]> {
  return (await apiClient.get<InviteWire[]>(`${base(projectId)}/invites`)).map(toInvite);
}

export async function createInvite(
  projectId: string,
  email: string,
  role: InviteRole,
): Promise<InviteCreated> {
  const wire = await apiClient.post<Schemas["InviteCreated"]>(`${base(projectId)}/invites`, {
    email,
    role,
  });
  return { ...toInvite(wire), token: wire.token };
}

export async function revokeInvite(projectId: string, inviteId: string): Promise<void> {
  await apiClient.delete(`${base(projectId)}/invites/${inviteId}`);
}

export async function getInvitePreview(token: string): Promise<InvitePreview> {
  const w = await apiClient.get<Schemas["InvitePreview"]>(`/api/v1/invites/${token}`);
  return {
    projectId: w.project_id,
    projectName: w.project_name,
    inviterName: w.inviter_name,
    role: w.role as InviteRole,
    email: w.email,
  };
}

export async function acceptInvite(token: string): Promise<AcceptResult> {
  const w = await apiClient.post<Schemas["AcceptResponse"]>(`/api/v1/invites/${token}/accept`);
  return { projectId: w.project_id, role: w.role as Role };
}

export async function declineInvite(token: string): Promise<void> {
  await apiClient.post(`/api/v1/invites/${token}/decline`);
}

export async function listShareLinks(projectId: string): Promise<ShareLink[]> {
  return (await apiClient.get<Schemas["ShareLinkRead"][]>(`${base(projectId)}/share-links`)).map(toShareLink);
}

export async function createShareLink(projectId: string, role: LinkRole): Promise<ShareLinkCreated> {
  const wire = await apiClient.post<Schemas["ShareLinkCreated"]>(`${base(projectId)}/share-links`, { role });
  return { ...toShareLink(wire), token: wire.token, url: wire.url };
}

export async function revokeShareLink(projectId: string, linkId: string): Promise<void> {
  await apiClient.delete(`${base(projectId)}/share-links/${linkId}`);
}

export async function getSharePreview(token: string): Promise<SharePreview> {
  const w = await apiClient.get<Schemas["SharePreview"]>(`/api/v1/share-links/${token}`);
  return {
    projectId: w.project_id,
    projectName: w.project_name,
    ownerName: w.owner_name,
    role: w.role as LinkRole,
    alreadyMemberRole: (w.already_member_role ?? null) as Role | null,
  };
}

export async function joinShareLink(token: string): Promise<JoinResult> {
  const w = await apiClient.post<Schemas["ShareLinkJoined"]>(`/api/v1/share-links/${token}/join`);
  return { projectId: w.project_id, role: w.role as Role };
}

export interface Permissions {
  role: Role;
  capabilities: string[];
  /** The caller's Suggesting preference in the project (spec 119); absent from older servers. */
  suggest_mode?: boolean;
}

export async function getPermissions(projectId: string): Promise<Permissions> {
  return apiClient.get<Permissions>(`${base(projectId)}/permissions`);
}
