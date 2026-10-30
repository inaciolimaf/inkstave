/** A single diff hunk in the text's flow, with its decision in the margin (specs 47, 106). */
import { useTranslation } from "react-i18next";

import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";

import type { DiffHunk, LineType } from "./types";

const MARKER: Record<LineType, string> = { add: "+", del: "\u2212", ctx: " " };
const ROW_CLASS: Record<LineType, string> = {
  add: "bg-success-soft text-success-text",
  del: "bg-error-soft text-error-text",
  ctx: "text-foreground",
};
const GUTTER_CLASS: Record<LineType, string> = { add: "", del: "", ctx: "text-muted-foreground" };

export function HunkView({
  hunk,
  accepted,
  blocked,
  onToggle,
}: {
  hunk: DiffHunk;
  accepted: boolean;
  blocked: boolean;
  onToggle: () => void;
}) {
  const { t } = useTranslation("review");
  let oldNo = hunk.oldStart;
  let newNo = hunk.newStart;
  return (
    <div className="flex flex-col gap-2 py-3 sm:flex-row sm:gap-3">
      <div className={cn("min-w-0 flex-1 font-mono text-small", blocked && "opacity-60")}>
        <div className="truncate pb-1 text-muted-foreground">{hunk.header}</div>
        <div className="overflow-x-auto">
          {hunk.lines.map((line, i) => {
            const oldLabel = line.type === "add" ? "" : String(oldNo++);
            const newLabel = line.type === "del" ? "" : String(newNo++);
            const sr = line.type === "add" ? t("hunk.added") : line.type === "del" ? t("hunk.removed") : "";
            return (
              <div key={i} className={cn("flex whitespace-pre-wrap", ROW_CLASS[line.type])}>
                <span className={cn("w-8 shrink-0 select-none text-right", GUTTER_CLASS[line.type])}>
                  {oldLabel}
                </span>
                <span className={cn("w-8 shrink-0 select-none text-right", GUTTER_CLASS[line.type])}>
                  {newLabel}
                </span>
                <span className="w-4 shrink-0 select-none text-center" aria-hidden="true">
                  {MARKER[line.type]}
                </span>
                {sr && <span className="sr-only">{sr}: </span>}
                <span className="min-w-0 flex-1 break-words">{line.text}</span>
              </div>
            );
          })}
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 sm:w-28 sm:shrink-0 sm:flex-col sm:items-start sm:border-l sm:border-border sm:pl-3">
        <label className="flex items-center gap-2 text-small">
          <span>{accepted ? t("hunk.accept") : t("hunk.reject")}</span>
          <Switch
            checked={accepted && !blocked}
            disabled={blocked}
            onCheckedChange={onToggle}
            aria-label={t("hunk.acceptChange", { header: hunk.header })}
          />
        </label>
        {blocked && <span className="text-small text-error-text">{t("hunk.noLongerApplies")}</span>}
      </div>
    </div>
  );
}
