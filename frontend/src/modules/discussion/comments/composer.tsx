/** The box for a new comment on the selected text, at the top of the panel (spec 118). */
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";

import { type MentionCandidate, mentionIds } from "./mentions";
import { MentionTextarea } from "./mention-textarea";

export interface CommentComposerProps {
  quote: string;
  members: MentionCandidate[];
  pending: boolean;
  onSubmit: (body: string, mentions: string[]) => void;
  onCancel: () => void;
}

export function CommentComposer({ quote, members, pending, onSubmit, onCancel }: CommentComposerProps) {
  const { t } = useTranslation("discussion");
  const [body, setBody] = useState("");
  const [picked, setPicked] = useState<MentionCandidate[]>([]);

  const send = () => {
    const text = body.trim();
    if (text && !pending) onSubmit(text, mentionIds(text, picked));
  };

  return (
    <section
      aria-label={t("comments.composer.label")}
      className="space-y-2 rounded-md border border-primary p-3"
    >
      <p className="line-clamp-2 border-l-2 border-warning pl-2 text-small text-muted-foreground">
        “{quote}”
      </p>
      <MentionTextarea
        id="comment-composer"
        label={t("comments.composer.label")}
        value={body}
        onChange={setBody}
        onPick={(m) => setPicked((p) => [...p, m])}
        members={members}
        placeholder={t("comments.composer.placeholder")}
        rows={3}
        onSubmit={send}
      />
      <div className="flex items-center justify-between gap-2">
        <span className="text-small text-muted-foreground">{t("comments.mentions.hint")}</span>
        <div className="flex gap-2">
          <Button size="sm" variant="ghost" onClick={onCancel}>
            {t("comments.cancel")}
          </Button>
          <Button size="sm" onClick={send} disabled={!body.trim() || pending}>
            {t("comments.composer.submit")}
          </Button>
        </div>
      </div>
    </section>
  );
}
