import { FileText } from "lucide-react";

/** Shown before any compile has run (spec 24, §5.3.7). */
export function PreviewEmptyState() {
  return (
    <div
      className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center text-sm text-muted-foreground"
      aria-label="No preview yet"
    >
      <FileText className="size-8" aria-hidden="true" />
      <p>Compile to see a preview of your document.</p>
    </div>
  );
}
