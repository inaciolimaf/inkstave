/** "People with access" list: role controls, transfer/remove/leave actions (spec 33). */
import { useTranslation } from "react-i18next";

import { QueryView } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";

import type { Confirm } from "./ConfirmDialog";
import type { InviteRole, Member } from "./types";

interface MemberActions {
  isOwner: boolean;
  currentUserId: string | undefined;
  onChangeRole: (userId: string, role: InviteRole) => void;
  onConfirm: (confirm: Confirm) => void;
  onTransfer: (userId: string) => void;
  onRemove: (userId: string) => void;
}

interface MembersListProps extends MemberActions {
  members: Member[];
  isLoading: boolean;
  isError: boolean;
  refetch: () => void;
}

function MemberRoleSelect({
  member,
  onChangeRole,
}: {
  member: Member;
  onChangeRole: MemberActions["onChangeRole"];
}) {
  const { t } = useTranslation(["sharing", "common"]);
  return (
    <Select value={member.role} onValueChange={(v) => onChangeRole(member.userId, v as InviteRole)}>
      <SelectTrigger className="w-24 capitalize" aria-label={t("members.roleFor", { name: member.name })}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="editor" className="capitalize">
          {t("role.editor")}
        </SelectItem>
        <SelectItem value="viewer" className="capitalize">
          {t("role.viewer")}
        </SelectItem>
      </SelectContent>
    </Select>
  );
}

/** What the owner can do to another member: both actions ask first. */
function OwnerActions({
  member,
  onConfirm,
  onTransfer,
  onRemove,
}: { member: Member } & Pick<MemberActions, "onConfirm" | "onTransfer" | "onRemove">) {
  const { t } = useTranslation(["sharing", "common"]);
  return (
    <>
      <Button
        size="sm"
        variant="ghost"
        onClick={() =>
          onConfirm({
            title: t("members.transferConfirm.title", { name: member.name }),
            description: t("members.transferConfirm.description"),
            action: t("members.transferConfirm.action"),
            run: () => onTransfer(member.userId),
          })
        }
      >
        {t("members.transfer")}
      </Button>
      <Button
        size="sm"
        variant="ghost"
        aria-label={t("members.removeLabel", { name: member.name })}
        onClick={() =>
          onConfirm({
            title: t("members.removeConfirm.title", { name: member.name }),
            description: t("members.removeConfirm.description"),
            action: t("members.removeConfirm.action"),
            run: () => onRemove(member.userId),
          })
        }
      >
        {t("members.remove")}
      </Button>
    </>
  );
}

function LeaveButton({ onLeave, onConfirm }: { onLeave: () => void; onConfirm: MemberActions["onConfirm"] }) {
  const { t } = useTranslation(["sharing", "common"]);
  return (
    <Button
      size="sm"
      variant="ghost"
      onClick={() =>
        onConfirm({
          title: t("members.leaveConfirm.title"),
          description: t("members.leaveConfirm.description"),
          action: t("members.leaveConfirm.action"),
          run: onLeave,
        })
      }
    >
      {t("members.leave")}
    </Button>
  );
}

function MemberRow({ member, ...actions }: { member: Member } & MemberActions) {
  const { t } = useTranslation(["sharing", "common"]);
  const { isOwner, currentUserId, onChangeRole, onConfirm, onTransfer, onRemove } = actions;
  const manageable = isOwner && member.role !== "owner";
  const isSelf = member.userId === currentUserId;

  return (
    <li className="flex items-center gap-2 text-body">
      <div className="mr-auto min-w-0">
        <p className="truncate font-medium">
          {member.name}
          {isSelf && t("members.you")}
        </p>
        <p className="truncate text-small text-muted-foreground">{member.email}</p>
      </div>
      {member.viaLink && <span className="text-small text-muted-foreground">{t("members.viaLink")}</span>}
      {manageable ? (
        <MemberRoleSelect member={member} onChangeRole={onChangeRole} />
      ) : (
        <span className="text-small capitalize text-muted-foreground">{t(`role.${member.role}`)}</span>
      )}
      {manageable && (
        <OwnerActions member={member} onConfirm={onConfirm} onTransfer={onTransfer} onRemove={onRemove} />
      )}
      {!isOwner && isSelf && <LeaveButton onLeave={() => onRemove(member.userId)} onConfirm={onConfirm} />}
    </li>
  );
}

export function MembersList({ members, isLoading, isError, refetch, ...actions }: MembersListProps) {
  const { t } = useTranslation(["sharing", "common"]);
  return (
    <section aria-label={t("members.sectionLabel")} className="space-y-2">
      <h3 className="text-body font-medium">{t("members.title")}</h3>
      <QueryView
        query={{ data: members, isLoading, isError, refetch }}
        loading={
          <div className="space-y-2" data-testid="members-loading">
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-9 w-full" />
          </div>
        }
        errorMessage={t("members.loadError")}
      >
        {(loaded) => (
          <ul className="space-y-1">
            {loaded.map((m) => (
              <MemberRow key={m.userId} member={m} {...actions} />
            ))}
          </ul>
        )}
      </QueryView>
    </section>
  );
}
