/** The chat button in the editor bar, with the unread count on it (spec 117). */
import { MessageSquare } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";

export function ChatButton({ unread, onOpen }: { unread: number; onOpen: () => void }) {
  const { t } = useTranslation("discussion");
  return (
    <Button
      size="sm"
      variant="ghost"
      onClick={onOpen}
      aria-label={unread > 0 ? t("button.unreadAria", { count: unread }) : t("button.label")}
      className="relative"
    >
      <MessageSquare aria-hidden="true" className="size-4" />
      <span className="hidden md:inline">{t("button.label")}</span>
      {unread > 0 && (
        <span
          aria-hidden="true"
          className="absolute -right-0.5 -top-0.5 min-w-4 rounded-full bg-primary px-1 text-center text-small leading-4 text-primary-foreground"
        >
          {unread > 99 ? "99+" : unread}
        </span>
      )}
    </Button>
  );
}
