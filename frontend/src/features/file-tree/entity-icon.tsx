import { ChevronRight, File, FileText, Folder } from "lucide-react";

import type { EntityType } from "./types";

export function EntityIcon({ type }: { type: EntityType }) {
  if (type === "folder") return <Folder className="size-4 shrink-0 text-sky-600" aria-hidden />;
  if (type === "doc")
    return <FileText className="size-4 shrink-0 text-muted-foreground" aria-hidden />;
  return <File className="size-4 shrink-0 text-muted-foreground" aria-hidden />;
}

export function DisclosureChevron({ expanded }: { expanded: boolean }) {
  return (
    <ChevronRight
      className={`size-4 shrink-0 text-muted-foreground transition-transform ${expanded ? "rotate-90" : ""}`}
      aria-hidden
    />
  );
}
