/** The bar over the text while a proposal is reviewed inline: the counter, moving between changes, and the rest (spec 110). */
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";

export interface ReviewBarProps {
  /** 1-based index of the change the keyboard is on. */
  index: number;
  total: number;
  pending: number;
  readOnly: boolean;
  onPrevious: () => void;
  onNext: () => void;
  onAcceptAll: () => void;
  onRejectAll: () => void;
  onClose: () => void;
}

export function ReviewBar({
  index,
  total,
  pending,
  readOnly,
  onPrevious,
  onNext,
  onAcceptAll,
  onRejectAll,
  onClose,
}: ReviewBarProps) {
  const { t } = useTranslation("review");
  return (
    <div
      role="region"
      aria-label={t("bar.label")}
      className="flex flex-wrap items-center gap-x-2 gap-y-1 border-b bg-muted px-3 py-2 text-small"
    >
      <span className="font-medium tabular-nums" aria-live="polite">
        {t("bar.counter", { index, total })}
      </span>
      <div className="flex items-center gap-1">
        <Button size="sm" variant="ghost" onClick={onPrevious} aria-label={t("bar.previous")}>
          <span aria-hidden="true">↑</span>
          {t("bar.previous")}
        </Button>
        <Button size="sm" variant="ghost" onClick={onNext} aria-label={t("bar.next")}>
          <span aria-hidden="true">↓</span>
          {t("bar.next")}
        </Button>
      </div>
      <div className="ml-auto flex flex-wrap items-center gap-1">
        {!readOnly && (
          <>
            <Button size="sm" variant="outline" onClick={onAcceptAll} disabled={pending === 0}>
              {t("bar.acceptAll")}
            </Button>
            <Button size="sm" variant="outline" onClick={onRejectAll} disabled={pending === 0}>
              {t("bar.rejectAll")}
            </Button>
          </>
        )}
        <Button size="sm" variant="ghost" onClick={onClose}>
          {t("bar.close")}
        </Button>
      </div>
    </div>
  );
}
