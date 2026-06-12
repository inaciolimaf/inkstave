/** Owner-only list of pending invites with revoke action (spec 33). */
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";

import type { Confirm } from "./ConfirmDialog";
import type { Invite } from "./types";

export function PendingInvites({
  invites,
  onConfirm,
  onRevoke,
}: {
  invites: Invite[];
  onConfirm: (confirm: Confirm) => void;
  onRevoke: (inviteId: string) => void;
}) {
  const { t } = useTranslation("sharing");
  return (
    <section aria-label={t("pending.sectionLabel")} className="space-y-2">
      <h3 className="text-sm font-medium">{t("pending.title")}</h3>
      {invites.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("pending.empty")}</p>
      ) : (
        <ul className="space-y-1">
          {invites.map((inv) => (
            <li key={inv.id} className="flex items-center gap-2 text-sm">
              <span className="mr-auto truncate">{inv.email}</span>
              <span className="text-xs capitalize text-muted-foreground">
                {t(`role.${inv.role}`)}
              </span>
              <Button
                size="sm"
                variant="ghost"
                aria-label={t("pending.revokeLabel", { email: inv.email })}
                onClick={() =>
                  onConfirm({
                    title: t("pending.revokeConfirm.title", { email: inv.email }),
                    description: t("pending.revokeConfirm.description"),
                    action: t("pending.revokeConfirm.action"),
                    run: () => onRevoke(inv.id),
                  })
                }
              >
                {t("pending.revoke")}
              </Button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
