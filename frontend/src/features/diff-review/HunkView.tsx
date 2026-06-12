/** A single diff hunk with an accept/reject toggle and per-line markers (spec 47). */
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";

import type { DiffHunk } from "./types";

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
    <div className={cn("rounded-md border", blocked && "opacity-60")}>
      <div className="flex items-center gap-2 border-b bg-muted/40 px-2 py-1 font-mono text-xs">
        <span className="flex-1 truncate">{hunk.header}</span>
        {blocked && <Badge variant="destructive">{t("hunk.noLongerApplies")}</Badge>}
        <label className="flex items-center gap-1 font-sans">
          <span className="text-xs">{accepted ? t("hunk.accept") : t("hunk.reject")}</span>
          <Switch
            checked={accepted && !blocked}
            disabled={blocked}
            onCheckedChange={onToggle}
            aria-label={t("hunk.acceptChange", { header: hunk.header })}
          />
        </label>
      </div>
      <div className="overflow-x-auto font-mono text-xs">
        {hunk.lines.map((line, i) => {
          const oldLabel = line.type === "add" ? "" : String(oldNo++);
          const newLabel = line.type === "del" ? "" : String(newNo++);
          const marker = line.type === "add" ? "+" : line.type === "del" ? "-" : " ";
          const sr =
            line.type === "add"
              ? t("hunk.added")
              : line.type === "del"
                ? t("hunk.removed")
                : "";
          return (
            <div
              key={i}
              className={cn(
                "flex whitespace-pre-wrap",
                line.type === "add" && "bg-green-500/15",
                line.type === "del" && "bg-red-500/15",
              )}
            >
              <span className="w-8 shrink-0 select-none text-right text-muted-foreground/60">
                {oldLabel}
              </span>
              <span className="w-8 shrink-0 select-none text-right text-muted-foreground/60">
                {newLabel}
              </span>
              <span className="w-4 shrink-0 select-none text-center" aria-hidden="true">
                {marker}
              </span>
              {sr && <span className="sr-only">{sr}: </span>}
              <span className="min-w-0 flex-1">{line.text}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
