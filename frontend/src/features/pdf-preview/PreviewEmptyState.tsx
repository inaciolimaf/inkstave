import { FileText } from "lucide-react";
import { useTranslation } from "react-i18next";

/** Shown before any compile has run (spec 24, §5.3.7). */
export function PreviewEmptyState() {
  const { t } = useTranslation("preview");
  return (
    <div
      className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center text-sm text-muted-foreground"
      aria-label={t("empty.noPreview")}
    >
      <FileText className="size-8" aria-hidden="true" />
      <p>{t("empty.compileToPreview")}</p>
    </div>
  );
}
