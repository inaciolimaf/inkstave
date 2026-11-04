/**
 * The project chat window body (spec 117). It lives in the agent window's slot, under the
 * Agent | Chat switch, and marks the chat read while it is the visible view.
 */
import { type FormEvent, type KeyboardEvent, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/modules/auth";

import { ChatMessage } from "./chat-message";
import { type PendingMessage, useChat } from "./use-chat";
import { useChatUnread } from "./use-chat-unread";

const CHAT_BODY_MAX_LENGTH = 4000;
/** Within this many pixels of the top, the next older page is fetched. */
const LOAD_OLDER_THRESHOLD_PX = 48;
/** Within this many pixels of the bottom, the view follows new messages. */
const FOLLOW_THRESHOLD_PX = 64;

function PendingRow({ item, onRetry }: { item: PendingMessage; onRetry: () => void }) {
  const { t } = useTranslation("discussion");
  return (
    <li
      className="ml-auto flex max-w-[90%] flex-col items-end"
      data-pending={item.failed ? "failed" : "sending"}
    >
      <div className="min-w-0 break-words rounded-lg bg-accent px-3 py-2 text-body text-accent-foreground">
        <span className="whitespace-pre-wrap">{item.body}</span>
      </div>
      {item.failed ? (
        <span className="mt-1 flex items-center gap-2 text-small text-error-text">
          {t("message.failed")}
          <Button size="sm" variant="ghost" className="h-7" onClick={onRetry}>
            {t("message.retry")}
          </Button>
        </span>
      ) : (
        <span className="mt-1 text-small text-muted-foreground">{t("message.sending")}</span>
      )}
    </li>
  );
}

/** Keeps the scroll position honest: older pages keep the reader in place, new ones follow the bottom. */
function useScrollAnchors(messages: unknown[], pending: unknown[]) {
  const scroller = useRef<HTMLDivElement>(null);
  const followBottom = useRef(true);
  const heightBeforeOlder = useRef<number | null>(null);

  useLayoutEffect(() => {
    const el = scroller.current;
    if (!el) return;
    if (heightBeforeOlder.current !== null) {
      el.scrollTop += el.scrollHeight - heightBeforeOlder.current;
      heightBeforeOlder.current = null;
    } else if (followBottom.current) {
      el.scrollTop = el.scrollHeight;
    }
  }, [messages, pending]);

  const onScroll = (loadOlder: () => void, hasOlder: boolean, loadingOlder: boolean) => {
    const el = scroller.current;
    if (!el) return;
    followBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < FOLLOW_THRESHOLD_PX;
    if (el.scrollTop < LOAD_OLDER_THRESHOLD_PX && hasOlder && !loadingOlder) {
      heightBeforeOlder.current = el.scrollHeight;
      loadOlder();
    }
  };

  return { scroller, followBottom, heightBeforeOlder, onScroll };
}

export function ChatPanel({ projectId, active }: { projectId: string; active: boolean }) {
  const { t } = useTranslation("discussion");
  const { user } = useAuth();
  const chat = useChat(projectId);
  const { markRead } = useChatUnread(projectId);
  const [draft, setDraft] = useState("");
  const anchors = useScrollAnchors(chat.messages, chat.pending);

  // Reading happens when the chat is the visible view: on opening it and on each new message while open.
  const shownCount = chat.messages.length;
  useEffect(() => {
    if (active) void markRead();
  }, [active, shownCount, markRead]);

  const send = (event?: FormEvent) => {
    event?.preventDefault();
    if (!draft.trim()) return;
    anchors.followBottom.current = true;
    chat.send(draft);
    setDraft("");
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      send();
    }
  };

  const olderButton = chat.hasOlder && (
    <div className="flex justify-center pb-2">
      <Button
        size="sm"
        variant="ghost"
        disabled={chat.loadingOlder}
        onClick={() => {
          const el = anchors.scroller.current;
          if (el) anchors.heightBeforeOlder.current = el.scrollHeight;
          chat.loadOlder();
        }}
      >
        {t("loadOlder")}
      </Button>
    </div>
  );

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div
        ref={anchors.scroller}
        role="log"
        aria-label={t("title")}
        aria-live="polite"
        onScroll={() => anchors.onScroll(chat.loadOlder, chat.hasOlder, chat.loadingOlder)}
        className="min-h-0 flex-1 overflow-y-auto px-3 py-2"
      >
        {olderButton}
        {chat.loading && (
          <div className="space-y-2" role="status" aria-busy="true" aria-label={t("loading")}>
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-4 w-1/2" />
          </div>
        )}
        {chat.failed && <p className="text-small text-error-text">{t("loadFailed")}</p>}
        {!chat.loading && !chat.failed && chat.messages.length === 0 && chat.pending.length === 0 && (
          <p className="text-body text-muted-foreground">{t("empty")}</p>
        )}
        <ul className="flex flex-col gap-3">
          {chat.messages.map((message) => (
            <ChatMessage
              key={message.id}
              message={message}
              own={message.author?.id === user?.id}
              onDelete={(id) => void chat.remove(id)}
            />
          ))}
          {chat.pending.map((item) => (
            <PendingRow key={item.localId} item={item} onRetry={() => chat.retry(item)} />
          ))}
        </ul>
      </div>
      <form onSubmit={send} className="flex items-end gap-2 border-t p-2">
        <Textarea
          aria-label={t("composer.label")}
          placeholder={t("composer.placeholder")}
          value={draft}
          maxLength={CHAT_BODY_MAX_LENGTH}
          rows={2}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={onKeyDown}
          className="min-h-10 resize-none"
        />
        <Button type="submit" size="sm" disabled={!draft.trim()}>
          {t("composer.send")}
        </Button>
      </form>
    </div>
  );
}
