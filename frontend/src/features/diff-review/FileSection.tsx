/** Per-file diff section: header, accept/reject-all, and diff/preview toggle (spec 47). */
import { useState } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

import { HunkView } from "./HunkView";
import { ReadonlyCodePreview } from "./ReadonlyCodePreview";
import type { ProposedFileDiff } from "./types";

export function FileSection({
  file,
  decisions,
  blockedIds,
  baseChanged,
  onToggle,
  onSetAll,
  previewText,
}: {
  file: ProposedFileDiff;
  decisions: Record<string, boolean>;
  blockedIds: string[];
  baseChanged: boolean;
  onToggle: (hunkId: string) => void;
  onSetAll: (accepted: boolean) => void;
  previewText: string;
}) {
  const [showPreview, setShowPreview] = useState(false);
  const accepted = file.hunks.filter((h) => decisions[h.id] && !blockedIds.includes(h.id)).length;
  return (
    <section className="space-y-2" aria-label={`Changes to ${file.path}`}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{file.path}</span>
        {file.isNewFile && <Badge variant="secondary">New file</Badge>}
        {file.isDeletion && <Badge variant="destructive">Deleted</Badge>}
        <span className="text-xs text-muted-foreground">
          {accepted}/{file.hunks.length} hunks
        </span>
        <div className="ml-auto flex gap-1">
          <Button size="sm" variant="ghost" onClick={() => onSetAll(true)}>
            Accept all
          </Button>
          <Button size="sm" variant="ghost" onClick={() => onSetAll(false)}>
            Reject all
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setShowPreview((p) => !p)}>
            {showPreview ? "Diff" : "Preview"}
          </Button>
        </div>
      </div>
      {baseChanged && (
        <Alert variant="destructive" className="py-2">
          <AlertTitle className="text-sm">This file changed since the proposal</AlertTitle>
          <AlertDescription className="text-xs">
            Hunks that no longer apply are marked and will be skipped.
          </AlertDescription>
        </Alert>
      )}
      {showPreview ? (
        <ReadonlyCodePreview value={previewText} />
      ) : (
        <div className="space-y-2">
          {file.hunks.map((hunk) => (
            <HunkView
              key={hunk.id}
              hunk={hunk}
              accepted={!!decisions[hunk.id]}
              blocked={blockedIds.includes(hunk.id)}
              onToggle={() => onToggle(hunk.id)}
            />
          ))}
        </div>
      )}
    </section>
  );
}
