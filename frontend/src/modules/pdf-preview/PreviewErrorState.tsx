import { AlertTriangle } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";

import type { CompileJobStatus } from "./types";

type ErrorOutcome = Extract<CompileJobStatus, "failure" | "timeout" | "error">;

const COPY_KEYS: Record<ErrorOutcome, { title: string; message: string }> = {
  failure: { title: "errorState.failureTitle", message: "errorState.failureMessage" },
  timeout: { title: "errorState.timeoutTitle", message: "errorState.timeoutMessage" },
  error: { title: "errorState.errorTitle", message: "errorState.errorMessage" },
};

/** Failed / timed-out / errored compile messaging (spec 24, §5.3.7). */
export function PreviewErrorState({
  outcome,
  detail,
  onViewLog,
  onRetry,
}: {
  outcome: ErrorOutcome;
  detail?: string | null;
  onViewLog: () => void;
  onRetry: () => void;
}) {
  const { t } = useTranslation("preview");
  const copy = COPY_KEYS[outcome];
  return (
    <div
      role="alert"
      className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center text-sm"
    >
      <AlertTriangle className="size-8 text-destructive" aria-hidden="true" />
      <div className="space-y-1">
        <p className="font-medium text-destructive">{t(copy.title)}</p>
        <p className="text-muted-foreground">{detail || t(copy.message)}</p>
      </div>
      <div className="flex items-center gap-2">
        <Button size="sm" variant="outline" onClick={onViewLog}>
          {t("errorState.viewLog")}
        </Button>
        <Button size="sm" onClick={onRetry}>
          {t("errorState.tryAgain")}
        </Button>
      </div>
    </div>
  );
}
