/** "Share" modal: invite by email, manage members & pending invites (spec 33). */
import { useTranslation } from "react-i18next";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

import { ConfirmDialog } from "./ConfirmDialog";
import { InviteForm } from "./InviteForm";
import { MembersList } from "./MembersList";
import { PendingInvites } from "./PendingInvites";
import { useSharing } from "./useSharing";

export function ShareDialog({
  projectId,
  open,
  onOpenChange,
}: {
  projectId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { t } = useTranslation("sharing");
  const {
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
  } = useSharing(projectId, open);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{t("dialog.title")}</DialogTitle>
          <DialogDescription>{t("dialog.description")}</DialogDescription>
        </DialogHeader>

        {isOwner && (
          <InviteForm
            email={email}
            setEmail={setEmail}
            inviteRole={inviteRole}
            setInviteRole={setInviteRole}
            inviteError={inviteError}
            setInviteError={setInviteError}
            isPending={invite.isPending}
            onSubmit={() => invite.mutate()}
          />
        )}

        <MembersList
          members={members}
          isLoading={membersQuery.isLoading}
          isError={membersQuery.isError}
          refetch={() => void membersQuery.refetch()}
          isOwner={isOwner}
          currentUserId={user?.id}
          onChangeRole={(userId, role) => roleMutation.mutate({ userId, role })}
          onConfirm={setConfirm}
          onTransfer={(userId) => transfer.mutate(userId)}
          onRemove={(userId) => remove.mutate(userId)}
        />

        {isOwner && (
          <PendingInvites
            invites={invitesQuery.data ?? []}
            onConfirm={setConfirm}
            onRevoke={(inviteId) => revoke.mutate(inviteId)}
          />
        )}
      </DialogContent>

      <ConfirmDialog confirm={confirm} onClose={() => setConfirm(null)} />
    </Dialog>
  );
}
