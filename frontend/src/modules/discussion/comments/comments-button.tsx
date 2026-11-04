/** The editor-bar button that opens the comments panel, with the open-thread count (spec 118). */
import { MessageSquareQuote } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";

export function CommentsButton({ openCount, onOpen }: { openCount: number; onOpen: () => void }) {
  const { t } = useTranslation("discussion");
  return (
    <Button
      size="sm"
      variant="ghost"
      onClick={onOpen}
      aria-label={
        openCount > 0 ? t("comments.button.openAria", { count: openCount }) : t("comments.button.label")
      }
      className="relative"
    >
      <MessageSquareQuote aria-hidden="true" className="size-4" />
      <span className="hidden md:inline">{t("comments.button.label")}</span>
      {openCount > 0 && (
        <span
          aria-hidden="true"
          className="absolute -right-0.5 -top-0.5 min-w-4 rounded-full bg-warning px-1 text-center text-small leading-4 text-warning-on"
        >
          {openCount > 99 ? "99+" : openCount}
        </span>
      )}
    </Button>
  );
}
