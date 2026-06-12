/** Post-apply summary alert: per-file applied/skipped/error counts (spec 47, #190). */
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

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
  return (
    <Alert variant={variant} role={role}>
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription className="text-xs">
        {results.map((res) => (
          <div key={res.path}>
            {res.path}: {res.appliedHunks.length} applied
            {res.blockedHunks.length ? `, ${res.blockedHunks.length} skipped` : ""}
            {res.error ? ` — error: ${res.error}` : ""}
          </div>
        ))}
      </AlertDescription>
    </Alert>
  );
}
