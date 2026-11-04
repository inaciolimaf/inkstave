/**
 * The Suggestions tab of the review column (spec 119 §3): every suggested change of the document in text order,
 * with Accept all and Reject all for the document. Members who can write the text decide; a viewer only reads.
 * A suggestion whose place is gone shows "No longer applies" and can be dismissed.
 */
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export interface SuggestionRow {
  id: string;
  kind: "insert" | "delete";
  authorName: string;
  createdAt: string;
  /** The inserted text, or the deleted text. */
  text: string;
  stale: boolean;
}

export type SuggestionDecision = "accept" | "reject" | "dismiss";

export interface SuggestionsTabProps {
  rows: SuggestionRow[];
  /** False for a viewer: the rows are shown without the buttons. */
  canDecide: boolean;
  onDecide: (id: string, decision: SuggestionDecision) => void;
  onDecideAll: (decision: "accept" | "reject") => void;
}

function RowActions({
  row,
  onDecide,
}: {
  row: SuggestionRow;
  onDecide: (id: string, decision: SuggestionDecision) => void;
}) {
  const { t } = useTranslation("suggest");
  if (row.stale) {
    return (
      <Button size="sm" variant="outline" onClick={() => onDecide(row.id, "dismiss")}>
        {t("tab.dismiss")}
      </Button>
    );
  }
  return (
    <>
      <Button size="sm" variant="outline" onClick={() => onDecide(row.id, "accept")}>
        {t("tab.accept")}
      </Button>
      <Button size="sm" variant="outline" onClick={() => onDecide(row.id, "reject")}>
        {t("tab.reject")}
      </Button>
    </>
  );
}

function SuggestionRowView({
  row,
  canDecide,
  onDecide,
}: {
  row: SuggestionRow;
  canDecide: boolean;
  onDecide: (id: string, decision: SuggestionDecision) => void;
}) {
  const { t } = useTranslation("suggest");
  const kind = t(row.kind === "insert" ? "tab.insertion" : "tab.deletion");
  return (
    <article
      aria-label={t("tab.rowLabel", { kind, name: row.authorName })}
      className={cn("space-y-2 rounded-md border p-3 text-small", row.stale && "opacity-70")}
    >
      <p className="font-medium">
        {kind} {t("tab.by", { name: row.authorName })}
      </p>
      <p
        className={cn(
          "break-words",
          row.kind === "insert" ? "underline decoration-2" : "text-error-text line-through",
        )}
      >
        {row.text}
      </p>
      {row.stale && <p className="text-muted-foreground">{t("tab.stale")}</p>}
      {canDecide && (
        <div className="flex flex-wrap gap-2">
          <RowActions row={row} onDecide={onDecide} />
        </div>
      )}
    </article>
  );
}

export function SuggestionsTab({ rows, canDecide, onDecide, onDecideAll }: SuggestionsTabProps) {
  const { t } = useTranslation("suggest");
  if (rows.length === 0) {
    return <p className="py-6 text-center text-body text-muted-foreground">{t("tab.empty")}</p>;
  }
  return (
    <div className="space-y-3">
      {canDecide && (
        <div className="flex gap-2">
          <Button size="sm" onClick={() => onDecideAll("accept")}>
            {t("tab.acceptAll")}
          </Button>
          <Button size="sm" variant="outline" onClick={() => onDecideAll("reject")}>
            {t("tab.rejectAll")}
          </Button>
        </div>
      )}
      <ul className="space-y-2" aria-label={t("tab.label")}>
        {rows.map((row) => (
          <li key={row.id}>
            <SuggestionRowView row={row} canDecide={canDecide} onDecide={onDecide} />
          </li>
        ))}
      </ul>
    </div>
  );
}
