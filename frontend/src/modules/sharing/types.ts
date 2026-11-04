/** Sharing domain types (spec 33). */

export type Role = "owner" | "editor" | "viewer";
export type InviteRole = "editor" | "viewer";

export interface Member {
  userId: string;
  name: string;
  email: string;
  role: Role;
  status: string;
  /** Joined, or was upgraded, through a share link (spec 116). */
  viaLink: boolean;
}

/** A share link's role: a link never grants `owner` (spec 116). */
export type LinkRole = "viewer" | "editor";

/** An active share link as the owner lists it. The token is not part of it. */
export interface ShareLink {
  id: string;
  role: LinkRole;
  createdAt: string;
}

/** A freshly created link: its URL is shown once, so the caller keeps it. */
export interface ShareLinkCreated extends ShareLink {
  token: string;
  url: string;
}

export interface SharePreview {
  projectId: string;
  projectName: string;
  ownerName: string;
  role: LinkRole;
  alreadyMemberRole: Role | null;
}

export interface JoinResult {
  projectId: string;
  role: Role;
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
