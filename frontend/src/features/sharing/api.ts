/** Sharing API calls (spec 33). snake_case ↔ camelCase mapping lives here only. */
import { apiClient } from "@/lib/api-client";

import type {
  AcceptResult,
  Invite,
  InviteCreated,
  InvitePreview,
  InviteRole,
  Member,
  Role,
} from "./types";

interface MemberWire {
  user_id: string;
  name: string;
  email: string;
  role: Role;
  status: string;
}

interface InviteWire {
  id: string;
  email: string;
  role: InviteRole;
  status: string;
  expires_at: string;
  created_at: string;
}

function toMember(w: MemberWire): Member {
  return { userId: w.user_id, name: w.name, email: w.email, role: w.role, status: w.status };
}

function toInvite(w: InviteWire): Invite {
  return {
    id: w.id,
    email: w.email,
    role: w.role,
    status: w.status,
    expiresAt: w.expires_at,
    createdAt: w.created_at,
  };
}

const base = (projectId: string) => `/api/v1/projects/${projectId}`;

export async function listMembers(projectId: string): Promise<Member[]> {
  return (await apiClient.get<MemberWire[]>(`${base(projectId)}/members`)).map(toMember);
}

export async function changeMemberRole(
  projectId: string,
  userId: string,
  role: InviteRole,
): Promise<Member> {
  return toMember(
    await apiClient.patch<MemberWire>(`${base(projectId)}/members/${userId}`, { role }),
  );
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
  const wire = await apiClient.post<InviteWire & { token: string }>(`${base(projectId)}/invites`, {
    email,
    role,
  });
  return { ...toInvite(wire), token: wire.token };
}

export async function revokeInvite(projectId: string, inviteId: string): Promise<void> {
  await apiClient.delete(`${base(projectId)}/invites/${inviteId}`);
}

export async function getInvitePreview(token: string): Promise<InvitePreview> {
  const w = await apiClient.get<{
    project_id: string;
    project_name: string;
    inviter_name: string;
    role: InviteRole;
    email: string;
  }>(`/api/v1/invites/${token}`);
  return {
    projectId: w.project_id,
    projectName: w.project_name,
    inviterName: w.inviter_name,
    role: w.role,
    email: w.email,
  };
}

export async function acceptInvite(token: string): Promise<AcceptResult> {
  const w = await apiClient.post<{ project_id: string; role: Role }>(
    `/api/v1/invites/${token}/accept`,
  );
  return { projectId: w.project_id, role: w.role };
}

export async function declineInvite(token: string): Promise<void> {
  await apiClient.post(`/api/v1/invites/${token}/decline`);
}

export interface Permissions {
  role: Role;
  capabilities: string[];
}

export async function getPermissions(projectId: string): Promise<Permissions> {
  return apiClient.get<Permissions>(`${base(projectId)}/permissions`);
}
