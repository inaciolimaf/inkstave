/** Sharing domain types (spec 33). */

export type Role = "owner" | "editor" | "viewer";
export type InviteRole = "editor" | "viewer";

export interface Member {
  userId: string;
  name: string;
  email: string;
  role: Role;
  status: string;
}

export interface Invite {
  id: string;
  email: string;
  role: InviteRole;
  status: string;
  expiresAt: string;
  createdAt: string;
}

export interface InviteCreated extends Invite {
  token: string;
}

export interface InvitePreview {
  projectId: string;
  projectName: string;
  inviterName: string;
  role: InviteRole;
  email: string;
}

export interface AcceptResult {
  projectId: string;
  role: Role;
}
