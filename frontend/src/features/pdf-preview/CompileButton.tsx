import { Loader2, Play, X } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";

import { type CompileState, isActive } from "./types";

/**
 * The Compile / Cancel control (spec 24, §5.3.3). While a compile is active the
 * Compile button is disabled (showing the progress label) and a Cancel button
 * appears next to it; this is the client-side debounce against double submits.
 */
export function CompileButton({
  state,
  progressLabel,
  onCompile,
  onCancel,
}: {
  state: CompileState;
  progressLabel: string | null;
  onCompile: () => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation(["preview", "common"]);
  const active = isActive(state);

  if (active) {
    return (
      <div className="flex items-center gap-2">
        <Button size="sm" disabled aria-label={t("compile.progressLabel")} aria-disabled="true">
          <Loader2 className="animate-spin" aria-hidden="true" />
          {progressLabel ?? t("compile.compiling")}
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={onCancel}
          aria-label={t("compile.cancelCompilation")}
        >
          <X aria-hidden="true" />
          {t("common:action.cancel")}
        </Button>
      </div>
    );
  }

  return (
    <Button size="sm" onClick={onCompile} aria-label={t("compile.compileProject")}>
      <Play aria-hidden="true" />
      {t("compile.compile")}
    </Button>
  );
}
