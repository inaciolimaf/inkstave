/** "Online now" avatar stack for the editor toolbar (spec 32). */
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

import { initials } from "./colors";
import type { PresenceUser } from "./usePresence";

const DEFAULT_MAX = 5;

function describe(user: PresenceUser): string {
  const who = user.isLocal ? `${user.name} (You)` : user.name;
  return user.idle ? `${who} — idle` : `${who} — online`;
}

function PresenceAvatar({
  user,
  withTooltip = true,
}: {
  user: PresenceUser;
  withTooltip?: boolean;
}) {
  const avatar = (
    // `user.idle` comes from the same `state.idle` awareness field that the
    // remote-cursor fade reads (see remote-cursors.ts), so an idle peer's avatar
    // and caret dim together on other clients (spec 32 AC6).
    <Avatar
      className={cn(
        "size-7 border-2 bg-background ring-0 transition-opacity",
        user.idle && "opacity-50",
      )}
      style={{ borderColor: user.color }}
      aria-label={describe(user)}
    >
      <AvatarFallback style={{ color: user.color }}>{initials(user.name)}</AvatarFallback>
    </Avatar>
  );
  if (!withTooltip) return avatar;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span tabIndex={0} className="rounded-full focus:outline-none focus:ring-2 focus:ring-ring">
          {avatar}
        </span>
      </TooltipTrigger>
      <TooltipContent>{describe(user)}</TooltipContent>
    </Tooltip>
  );
}

export function OnlineUsers({ users, max = DEFAULT_MAX }: { users: PresenceUser[]; max?: number }) {
  if (users.length === 0) return null;
  const visible = users.slice(0, max);
  const overflow = users.slice(max);

  return (
    <TooltipProvider delayDuration={200}>
      <div className="flex items-center -space-x-2" role="list" aria-label="People online">
        {visible.map((user) => (
          <div role="listitem" key={user.id}>
            <PresenceAvatar user={user} />
          </div>
        ))}
        {overflow.length > 0 && (
          <Popover>
            <PopoverTrigger asChild>
              <button
                type="button"
                aria-label={`${overflow.length} more online`}
                className="flex size-7 items-center justify-center rounded-full border-2 border-background bg-muted text-xs font-medium text-muted-foreground"
              >
                +{overflow.length}
              </button>
            </PopoverTrigger>
            <PopoverContent className="w-48 p-2">
              <ul className="space-y-1">
                {overflow.map((user) => (
                  <li key={user.id} className="flex items-center gap-2 text-sm">
                    <span
                      className="size-2 shrink-0 rounded-full"
                      style={{ backgroundColor: user.color }}
                      aria-hidden="true"
                    />
                    <span className={cn("truncate", user.idle && "text-muted-foreground")}>
                      {describe(user)}
                    </span>
                  </li>
                ))}
              </ul>
            </PopoverContent>
          </Popover>
        )}
      </div>
    </TooltipProvider>
  );
}
