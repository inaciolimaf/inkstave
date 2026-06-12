import { AlertTriangle } from "lucide-react";

import { Button } from "@/components/ui/button";

import type { CompileJobStatus } from "./types";

type ErrorOutcome = Extract<CompileJobStatus, "failure" | "timeout" | "error">;

const COPY: Record<ErrorOutcome, { title: string; message: string }> = {
  failure: {
    title: "Compilation failed",
    message: "Your document didn’t compile. Check the log for the LaTeX errors.",
  },
  timeout: {
    title: "Compilation timed out",
    message: "The compile took too long and was stopped. Simplify the document or try again.",
  },
  error: {
    title: "Something went wrong",
    message: "The compile couldn’t be completed due to a system error.",
  },
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
  const copy = COPY[outcome];
  return (
    <div
      role="alert"
      className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center text-sm"
    >
      <AlertTriangle className="size-8 text-destructive" aria-hidden="true" />
      <div className="space-y-1">
        <p className="font-medium text-destructive">{copy.title}</p>
        <p className="text-muted-foreground">{detail || copy.message}</p>
      </div>
      <div className="flex items-center gap-2">
        <Button size="sm" variant="outline" onClick={onViewLog}>
          View log
        </Button>
        <Button size="sm" onClick={onRetry}>
          Try again
        </Button>
      </div>
    </div>
  );
}
