/** "People with access" list: role controls, transfer/remove/leave actions (spec 33). */
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";

import type { Confirm } from "./ConfirmDialog";
import type { InviteRole, Member } from "./types";

interface MembersListProps {
  members: Member[];
  isLoading: boolean;
  isError: boolean;
  refetch: () => void;
  isOwner: boolean;
  currentUserId: string | undefined;
  onChangeRole: (userId: string, role: InviteRole) => void;
  onConfirm: (confirm: Confirm) => void;
  onTransfer: (userId: string) => void;
  onRemove: (userId: string) => void;
}

export function MembersList({
  members,
  isLoading,
  isError,
  refetch,
  isOwner,
  currentUserId,
  onChangeRole,
  onConfirm,
  onTransfer,
  onRemove,
}: MembersListProps) {
  const { t } = useTranslation(["sharing", "common"]);
  return (
    <section aria-label={t("members.sectionLabel")} className="space-y-2">
      <h3 className="text-sm font-medium">{t("members.title")}</h3>
      {isLoading && (
        <div className="space-y-2" data-testid="members-loading">
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-9 w-full" />
        </div>
      )}
      {isError && (
        <div className="flex items-center gap-2 text-sm text-destructive" role="alert">
          {t("members.loadError")}
          <Button size="sm" variant="outline" onClick={() => refetch()}>
            {t("common:action.retry")}
          </Button>
        </div>
      )}
      <ul className="space-y-1">
        {members.map((m) => (
          <li key={m.userId} className="flex items-center gap-2 text-sm">
            <div className="mr-auto min-w-0">
              <p className="truncate font-medium">
                {m.name}
                {m.userId === currentUserId && t("members.you")}
              </p>
              <p className="truncate text-xs text-muted-foreground">{m.email}</p>
            </div>
            {isOwner && m.role !== "owner" ? (
              <Select
                value={m.role}
                onValueChange={(v) => onChangeRole(m.userId, v as InviteRole)}
              >
                <SelectTrigger
                  className="w-24 capitalize"
                  aria-label={t("members.roleFor", { name: m.name })}
                >
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
            ) : (
              <span className="text-xs capitalize text-muted-foreground">
                {t(`role.${m.role}`)}
              </span>
            )}
            {isOwner && m.role !== "owner" && (
              <>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() =>
                    onConfirm({
                      title: t("members.transferConfirm.title", { name: m.name }),
                      description: t("members.transferConfirm.description"),
                      action: t("members.transferConfirm.action"),
                      run: () => onTransfer(m.userId),
                    })
                  }
                >
                  {t("members.transfer")}
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  aria-label={t("members.removeLabel", { name: m.name })}
                  onClick={() =>
                    onConfirm({
                      title: t("members.removeConfirm.title", { name: m.name }),
                      description: t("members.removeConfirm.description"),
                      action: t("members.removeConfirm.action"),
                      run: () => onRemove(m.userId),
                    })
                  }
                >
                  {t("members.remove")}
                </Button>
              </>
            )}
            {!isOwner && m.userId === currentUserId && (
              <Button
                size="sm"
                variant="ghost"
                onClick={() =>
                  onConfirm({
                    title: t("members.leaveConfirm.title"),
                    description: t("members.leaveConfirm.description"),
                    action: t("members.leaveConfirm.action"),
                    run: () => onRemove(m.userId),
                  })
                }
              >
                {t("members.leave")}
              </Button>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
