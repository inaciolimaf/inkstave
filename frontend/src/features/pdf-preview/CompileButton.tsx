import { Loader2, Play, X } from "lucide-react";

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
  const active = isActive(state);

  if (active) {
    return (
      <div className="flex items-center gap-2">
        <Button size="sm" disabled aria-label="Compiling" aria-disabled="true">
          <Loader2 className="animate-spin" aria-hidden="true" />
          {progressLabel ?? "Compiling…"}
        </Button>
        <Button size="sm" variant="outline" onClick={onCancel} aria-label="Cancel compilation">
          <X aria-hidden="true" />
          Cancel
        </Button>
      </div>
    );
  }

  return (
    <Button size="sm" onClick={onCompile} aria-label="Compile project">
      <Play aria-hidden="true" />
      Compile
    </Button>
  );
}
