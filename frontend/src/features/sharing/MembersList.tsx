/** "People with access" list: role controls, transfer/remove/leave actions (spec 33). */
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
  return (
    <section aria-label="People with access" className="space-y-2">
      <h3 className="text-sm font-medium">People with access</h3>
      {isLoading && (
        <div className="space-y-2" data-testid="members-loading">
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-9 w-full" />
        </div>
      )}
      {isError && (
        <div className="flex items-center gap-2 text-sm text-destructive" role="alert">
          Couldn’t load members.
          <Button size="sm" variant="outline" onClick={() => refetch()}>
            Retry
          </Button>
        </div>
      )}
      <ul className="space-y-1">
        {members.map((m) => (
          <li key={m.userId} className="flex items-center gap-2 text-sm">
            <div className="mr-auto min-w-0">
              <p className="truncate font-medium">
                {m.name}
                {m.userId === currentUserId && " (You)"}
              </p>
              <p className="truncate text-xs text-muted-foreground">{m.email}</p>
            </div>
            {isOwner && m.role !== "owner" ? (
              <Select
                value={m.role}
                onValueChange={(v) => onChangeRole(m.userId, v as InviteRole)}
              >
                <SelectTrigger className="w-24" aria-label={`Role for ${m.name}`}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="editor">Editor</SelectItem>
                  <SelectItem value="viewer">Viewer</SelectItem>
                </SelectContent>
              </Select>
            ) : (
              <span className="text-xs capitalize text-muted-foreground">{m.role}</span>
            )}
            {isOwner && m.role !== "owner" && (
              <>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() =>
                    onConfirm({
                      title: `Make ${m.name} the owner?`,
                      description: "You will become an editor. This cannot be undone here.",
                      action: "Transfer",
                      run: () => onTransfer(m.userId),
                    })
                  }
                >
                  Transfer
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  aria-label={`Remove ${m.name}`}
                  onClick={() =>
                    onConfirm({
                      title: `Remove ${m.name}?`,
                      description: "They will lose access to this project.",
                      action: "Remove",
                      run: () => onRemove(m.userId),
                    })
                  }
                >
                  Remove
                </Button>
              </>
            )}
            {!isOwner && m.userId === currentUserId && (
              <Button
                size="sm"
                variant="ghost"
                onClick={() =>
                  onConfirm({
                    title: "Leave this project?",
                    description: "You will lose access until invited again.",
                    action: "Leave",
                    run: () => onRemove(m.userId),
                  })
                }
              >
                Leave project
              </Button>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
