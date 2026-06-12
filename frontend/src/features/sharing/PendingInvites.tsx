/** Owner-only list of pending invites with revoke action (spec 33). */
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
  return (
    <section aria-label="Pending invites" className="space-y-2">
      <h3 className="text-sm font-medium">Pending invites</h3>
      {invites.length === 0 ? (
        <p className="text-sm text-muted-foreground">No pending invites.</p>
      ) : (
        <ul className="space-y-1">
          {invites.map((inv) => (
            <li key={inv.id} className="flex items-center gap-2 text-sm">
              <span className="mr-auto truncate">{inv.email}</span>
              <span className="text-xs capitalize text-muted-foreground">{inv.role}</span>
              <Button
                size="sm"
                variant="ghost"
                aria-label={`Revoke invite for ${inv.email}`}
                onClick={() =>
                  onConfirm({
                    title: `Revoke invite for ${inv.email}?`,
                    description: "The invitation link will stop working.",
                    action: "Revoke",
                    run: () => onRevoke(inv.id),
                  })
                }
              >
                Revoke
              </Button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
