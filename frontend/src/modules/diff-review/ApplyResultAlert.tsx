/** Post-apply summary alert: per-file applied/skipped/error counts (spec 47, #190). */
import { useTranslation } from "react-i18next";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { cn } from "@/lib/utils";

import type { ApplyFileResult } from "./types";

/**
 * Renders the per-file apply summary shared by the "applied" and "error" phases.
 * Pass `variant="destructive"` + `role="alert"` for the failure case; the success
 * case uses the default Alert with no role override.
 */
export function ApplyResultAlert({
  title,
  results,
  variant,
  role,
}: {
  title: string;
  results: ApplyFileResult[];
  variant?: "destructive";
  role?: "alert";
}) {
  const { t } = useTranslation("review");
  return (
    <Alert
      variant={variant}
      role={role}
      className={cn(
        "rounded-none border-0 border-l-2 px-3 py-1",
        variant ? "border-error-text dark:border-error-text" : "border-success",
      )}
    >
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription className="text-small">
        {results.map((res) => (
          <div key={res.path}>
            {res.path}: {t("applyResult.applied", { count: res.appliedHunks.length })}
            {res.blockedHunks.length ? t("applyResult.skipped", { count: res.blockedHunks.length }) : ""}
            {res.error ? t("applyResult.error", { error: res.error }) : ""}
          </div>
        ))}
      </AlertDescription>
    </Alert>
  );
}
