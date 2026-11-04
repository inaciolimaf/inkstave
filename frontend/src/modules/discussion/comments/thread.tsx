/** One comment thread: its quote, messages, reply box and resolve (spec 118). */
import { useId, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { formatDateTime } from "@/lib/formatting";
import { cn } from "@/lib/utils";

import type { CommentMessage, CommentThread } from "./api";
import { type MentionCandidate, mentionIds } from "./mentions";
import { MentionTextarea } from "./mention-textarea";
import { useCommentMutations } from "./use-comments";

export interface ThreadViewProps {
  projectId: string;
  thread: CommentThread;
  /** The text the thread was on has been removed. */
  detached: boolean;
  members: MentionCandidate[];
  meId: string | null;
  onOpen?: () => void;
  /** Open in the editor when the quote is pressed. */
  selected: boolean;
}

/** The author's display name, `You` for the viewer, or the former-member label. */
function AuthorName({ message, meId }: { message: CommentMessage; meId: string | null }) {
  const { t } = useTranslation("discussion");
  if (!message.author) return <span className="font-medium">{t("comments.formerMember")}</span>;
  if (message.author.id === meId) return <span className="font-medium">{t("comments.you")}</span>;
  return <span className="font-medium">{message.author.display_name}</span>;
}

function MessageEditor({
  initial,
  members,
  onSave,
  onCancel,
}: {
  initial: { body: string; mentions: string[] };
  members: MentionCandidate[];
  onSave: (body: string, mentions: string[]) => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation("discussion");
  const id = useId();
  const [body, setBody] = useState(initial.body);
  const [picked, setPicked] = useState<MentionCandidate[]>(
    members.filter((m) => initial.mentions.includes(m.id)),
  );
  const save = () => {
    const text = body.trim();
    if (text) onSave(text, mentionIds(text, picked));
  };
  return (
    <div className="space-y-2">
      <MentionTextarea
        id={`edit-${id}`}
        label={t("comments.edit")}
        value={body}
        onChange={setBody}
        onPick={(m) => setPicked((p) => [...p, m])}
        members={members}
        onSubmit={save}
      />
      <div className="flex justify-end gap-2">
        <Button size="sm" variant="ghost" onClick={onCancel}>
          {t("comments.cancel")}
        </Button>
        <Button size="sm" onClick={save} disabled={!body.trim()}>
          {t("comments.save")}
        </Button>
      </div>
    </div>
  );
}

function MessageItem({
  projectId,
  threadId,
  message,
  mine,
  members,
  meId,
}: {
  projectId: string;
  threadId: string;
  message: CommentMessage;
  mine: boolean;
  members: MentionCandidate[];
  meId: string | null;
}) {
  const { t } = useTranslation("discussion");
  const { edit, remove } = useCommentMutations(projectId);
  const [editing, setEditing] = useState(false);

  if (message.deleted) {
    return (
      <li className="text-small italic text-muted-foreground">
        {t("comments.messageDeleted")} · {formatDateTime(message.created_at)}
      </li>
    );
  }

  return (
    <li className="space-y-1">
      <div className="flex flex-wrap items-baseline gap-x-2 text-small text-muted-foreground">
        <span className="text-foreground">
          <AuthorName message={message} meId={meId} />
        </span>
        <time dateTime={message.created_at}>{formatDateTime(message.created_at)}</time>
        {message.edited_at && <span>· {t("comments.edited")}</span>}
      </div>
      {editing ? (
        <MessageEditor
          initial={{ body: message.body ?? "", mentions: message.mentions }}
          members={members}
          onCancel={() => setEditing(false)}
          onSave={(body, mentions) =>
            edit.mutate(
              { threadId, messageId: message.id, body, mentions },
              { onSuccess: () => setEditing(false) },
            )
          }
        />
      ) : (
        <p className="whitespace-pre-wrap break-words text-body">{message.body}</p>
      )}
      {mine && !editing && (
        <div className="flex gap-3 text-small">
          <button
            type="button"
            className="text-muted-foreground hover:text-foreground"
            onClick={() => setEditing(true)}
          >
            {t("comments.edit")}
          </button>
          <button
            type="button"
            className="text-muted-foreground hover:text-foreground"
            onClick={() => remove.mutate({ threadId, messageId: message.id })}
          >
            {t("comments.delete")}
          </button>
        </div>
      )}
    </li>
  );
}

function ReplyBox({
  projectId,
  threadId,
  members,
}: {
  projectId: string;
  threadId: string;
  members: MentionCandidate[];
}) {
  const { t } = useTranslation("discussion");
  const { reply } = useCommentMutations(projectId);
  const [body, setBody] = useState("");
  const [picked, setPicked] = useState<MentionCandidate[]>([]);

  const send = () => {
    const text = body.trim();
    if (!text) return;
    reply.mutate(
      { threadId, body: text, mentions: mentionIds(text, picked) },
      {
        onSuccess: () => {
          setBody("");
          setPicked([]);
        },
      },
    );
  };

  return (
    <div className="space-y-2">
      <MentionTextarea
        id={`reply-${threadId}`}
        label={t("comments.reply.label")}
        value={body}
        onChange={setBody}
        onPick={(m) => setPicked((p) => [...p, m])}
        members={members}
        placeholder={t("comments.reply.placeholder")}
        onSubmit={send}
      />
      <div className="flex items-center justify-between gap-2">
        <span className="text-small text-muted-foreground">{t("comments.mentions.hint")}</span>
        <Button size="sm" onClick={send} disabled={!body.trim() || reply.isPending}>
          {t("comments.reply.send")}
        </Button>
      </div>
    </div>
  );
}

export function ThreadView({
  projectId,
  thread,
  detached,
  members,
  meId,
  onOpen,
  selected,
}: ThreadViewProps) {
  const { t } = useTranslation("discussion");
  const { resolve } = useCommentMutations(projectId);
  const resolved = thread.resolved_at !== null;

  return (
    <section
      aria-label={t("comments.thread.label")}
      data-thread-id={thread.id}
      className={cn(
        "space-y-3 rounded-md border p-3",
        selected && "border-primary",
        resolved && "opacity-80",
      )}
    >
      <button
        type="button"
        onClick={onOpen}
        className="block w-full border-l-2 border-warning pl-2 text-left text-small text-muted-foreground"
      >
        <span className="line-clamp-3 break-words">“{thread.quoted_text}”</span>
      </button>
      {detached && (
        <p className="rounded bg-warning-soft px-2 py-1 text-small text-warning-text">
          <span className="font-medium">{t("comments.detached")}</span> · {t("comments.detachedNotice")}
        </p>
      )}
      <ul className="space-y-3" aria-label={t("comments.thread.messages")}>
        {thread.messages.map((message) => (
          <MessageItem
            key={message.id}
            projectId={projectId}
            threadId={thread.id}
            message={message}
            mine={message.author?.id === meId && meId !== null}
            members={members}
            meId={meId}
          />
        ))}
      </ul>
      {!resolved && <ReplyBox projectId={projectId} threadId={thread.id} members={members} />}
      <div className="flex justify-end">
        <Button
          size="sm"
          variant="outline"
          disabled={resolve.isPending}
          onClick={() => resolve.mutate({ threadId: thread.id, resolved: !resolved })}
        >
          {resolved ? t("comments.reopen") : t("comments.resolve")}
        </Button>
      </div>
    </section>
  );
}
