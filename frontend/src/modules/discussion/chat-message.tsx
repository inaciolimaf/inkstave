/** One chat message: who, when, and the text (spec 117). Own messages sit on the right. */
import { Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import type { ChatMessage as Message } from "./api";
import { ChatMarkdown } from "./chat-markdown";

function formatTime(iso: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, { hour: "2-digit", minute: "2-digit" }).format(new Date(iso));
}

export function ChatMessage({
  message,
  own,
  onDelete,
}: {
  message: Message;
  own: boolean;
  onDelete: (messageId: string) => void;
}) {
  const { t, i18n } = useTranslation("discussion");
  const name = message.author?.display_name ?? t("message.unknownAuthor");
  return (
    <li data-own={own} className={cn("flex max-w-[90%] flex-col", own ? "ml-auto items-end" : "items-start")}>
      <div className="mb-0.5 flex flex-wrap items-baseline gap-2 text-small">
        <span className="font-medium">{name}</span>
        <time dateTime={message.created_at} className="text-muted-foreground">
          {formatTime(message.created_at, i18n.language)}
        </time>
      </div>
      {message.deleted ? (
        <p className="text-small italic text-muted-foreground">{t("message.deleted")}</p>
      ) : (
        <div className="flex items-start gap-1">
          {own && (
            <Button
              size="icon"
              variant="ghost"
              className="order-first size-6 shrink-0"
              aria-label={t("message.delete")}
              onClick={() => onDelete(message.id)}
            >
              <Trash2 aria-hidden="true" className="size-3.5" />
            </Button>
          )}
          <div
            className={cn(
              "min-w-0 rounded-lg px-3 py-2",
              own ? "bg-accent text-accent-foreground" : "border border-border",
            )}
          >
            <ChatMarkdown>{message.body ?? ""}</ChatMarkdown>
          </div>
        </div>
      )}
    </li>
  );
}
