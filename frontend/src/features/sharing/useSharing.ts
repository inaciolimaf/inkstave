/** State, queries and mutations backing the Share dialog (spec 33). */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { useAuth } from "@/auth/auth-context";
import { ApiError } from "@/lib/api-client";

import {
  changeMemberRole,
  createInvite,
  listInvites,
  listMembers,
  removeMember,
  revokeInvite,
  transferOwnership,
} from "./api";
import type { Confirm } from "./ConfirmDialog";
import type { InviteRole } from "./types";

export const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError && error.message ? error.message : fallback;
}

export function useSharing(projectId: string, open: boolean) {
  const { user } = useAuth();
  const qc = useQueryClient();
  const [email, setEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<InviteRole>("editor");
  const [confirm, setConfirm] = useState<Confirm | null>(null);
  // Server-side invite errors (e.g. "already member") render inline near the field.
  const [inviteError, setInviteError] = useState<string | null>(null);

  const membersQuery = useQuery({
    queryKey: ["members", projectId],
    queryFn: () => listMembers(projectId),
    enabled: open,
  });
  const members = membersQuery.data ?? [];
  const isOwner = members.some((m) => m.userId === user?.id && m.role === "owner");

  const invitesQuery = useQuery({
    queryKey: ["invites", projectId],
    queryFn: () => listInvites(projectId),
    enabled: open && isOwner,
  });

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["members", projectId] });
    void qc.invalidateQueries({ queryKey: ["invites", projectId] });
  };

  const invite = useMutation({
    mutationFn: () => createInvite(projectId, email.trim(), inviteRole),
    onSuccess: () => {
      toast.success(`Invitation sent to ${email.trim()}`);
      setEmail("");
      setInviteError(null);
      invalidate();
    },
    // Server errors (e.g. "already member") surface inline under the field, not as a toast.
    onError: (e) => setInviteError(errorMessage(e, "Could not send the invitation.")),
  });

  const roleMutation = useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: InviteRole }) =>
      changeMemberRole(projectId, userId, role),
    onSuccess: invalidate,
    onError: (e) => toast.error(errorMessage(e, "Could not change the role.")),
  });

  const remove = useMutation({
    mutationFn: (userId: string) => removeMember(projectId, userId),
    onSuccess: invalidate,
    onError: (e) => toast.error(errorMessage(e, "Could not remove the member.")),
  });

  const revoke = useMutation({
    mutationFn: (inviteId: string) => revokeInvite(projectId, inviteId),
    onSuccess: invalidate,
    onError: (e) => toast.error(errorMessage(e, "Could not revoke the invite.")),
  });

  const transfer = useMutation({
    mutationFn: (userId: string) => transferOwnership(projectId, userId),
    onSuccess: () => {
      toast.success("Ownership transferred.");
      invalidate();
    },
    onError: (e) => toast.error(errorMessage(e, "Could not transfer ownership.")),
  });

  return {
    user,
    email,
    setEmail,
    inviteRole,
    setInviteRole,
    confirm,
    setConfirm,
    inviteError,
    setInviteError,
    membersQuery,
    members,
    isOwner,
    invitesQuery,
    invite,
    roleMutation,
    remove,
    revoke,
    transfer,
  };
}
