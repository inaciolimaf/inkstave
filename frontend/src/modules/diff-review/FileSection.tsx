/** Per-file diff section: header, accept/reject-all, and diff/preview toggle (spec 47). */
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

import { HunkView } from "./HunkView";
import { ReadonlyCodePreview } from "./ReadonlyCodePreview";
import type { ProposedFileDiff } from "./types";

export function FileSection({
  file,
  decisions,
  blockedIds,
  baseChanged,
  onToggle,
  onSetAll,
  previewText,
}: {
  file: ProposedFileDiff;
  decisions: Record<string, boolean>;
  blockedIds: string[];
  baseChanged: boolean;
  onToggle: (hunkId: string) => void;
  onSetAll: (accepted: boolean) => void;
  previewText: string;
}) {
  const { t } = useTranslation("review");
  const [showPreview, setShowPreview] = useState(false);
  const accepted = file.hunks.filter((h) => decisions[h.id] && !blockedIds.includes(h.id)).length;
  return (
    <section className="py-3 first:pt-0" aria-label={t("file.changesTo", { path: file.path })}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="break-all font-mono text-body font-medium">{file.path}</span>
        {file.isNewFile && <span className="text-small text-success-text">{t("file.newFile")}</span>}
        {file.isDeletion && <span className="text-small text-error-text">{t("file.deleted")}</span>}
        <span className="text-small tabular-nums text-muted-foreground">
          {t("file.hunkCount", { accepted, total: file.hunks.length })}
        </span>
        <div className="ml-auto flex gap-1">
          <Button size="sm" variant="ghost" onClick={() => onSetAll(true)}>
            {t("file.acceptAll")}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => onSetAll(false)}>
            {t("file.rejectAll")}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setShowPreview((p) => !p)}>
            {showPreview ? t("file.diff") : t("file.preview")}
          </Button>
        </div>
      </div>
      {baseChanged && (
        <Alert
          variant="destructive"
          className="mt-2 rounded-none border-0 border-l-2 border-error-text px-3 py-1 dark:border-error-text"
        >
          <AlertTitle className="text-body">{t("file.baseChangedTitle")}</AlertTitle>
          <AlertDescription className="text-small">{t("file.baseChangedDescription")}</AlertDescription>
        </Alert>
      )}
      {showPreview ? (
        <ReadonlyCodePreview value={previewText} />
      ) : (
        <div className="divide-y divide-border">
          {file.hunks.map((hunk) => (
            <HunkView
              key={hunk.id}
              hunk={hunk}
              accepted={!!decisions[hunk.id]}
              blocked={blockedIds.includes(hunk.id)}
              onToggle={() => onToggle(hunk.id)}
            />
          ))}
        </div>
      )}
    </section>
  );
}
