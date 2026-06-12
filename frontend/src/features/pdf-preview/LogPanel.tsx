import { Check, ChevronRight, Copy } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import type { CompileStatus } from "./types";

function statusLine(meta: CompileStatus | null): string | null {
  if (!meta) return null;
  const parts: string[] = [meta.status];
  if (meta.duration_ms != null) parts.push(`${(meta.duration_ms / 1000).toFixed(1)}s`);
  if (meta.exit_code != null) parts.push(`exit ${meta.exit_code}`);
  return parts.join(" · ");
}

/**
 * Collapsible raw compile-log viewer (spec 24, §5.3.6). Collapsed by default;
 * the parent auto-expands it on failure. The log is lazy-fetched the first time
 * the panel is open.
 */
export function LogPanel({
  expanded,
  onToggle,
  log,
  loading,
  error,
  onFetch,
  meta,
}: {
  expanded: boolean;
  onToggle: () => void;
  log: string | null;
  loading: boolean;
  error: string | null;
  onFetch: () => void;
  meta: CompileStatus | null;
}) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (expanded) onFetch();
  }, [expanded, onFetch]);

  useEffect(() => {
    if (!copied) return;
    const t = setTimeout(() => setCopied(false), 1500);
    return () => clearTimeout(t);
  }, [copied]);

  const copy = async () => {
    if (!log) return;
    try {
      await navigator.clipboard?.writeText(log);
      setCopied(true);
    } catch {
      /* clipboard unavailable — ignore */
    }
  };

  const line = statusLine(meta);

  return (
    <div className="flex flex-col border-t">
      <div className="flex items-center gap-2 px-3 py-1.5">
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={expanded}
          aria-controls="compile-log-region"
          className="flex items-center gap-1.5 text-sm font-medium hover:text-foreground/80"
        >
          <ChevronRight
            className={cn("size-4 transition-transform", expanded && "rotate-90")}
            aria-hidden="true"
          />
          Log
        </button>
        {line && <span className="truncate text-xs text-muted-foreground">{line}</span>}
        {expanded && log != null && (
          <Button
            size="sm"
            variant="ghost"
            className="ml-auto h-7"
            onClick={copy}
            aria-label="Copy log to clipboard"
          >
            {copied ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
            {copied ? "Copied" : "Copy"}
          </Button>
        )}
      </div>
      {expanded && (
        <div
          id="compile-log-region"
          role="region"
          aria-label="Compile log"
          tabIndex={0}
          className="max-h-48 overflow-auto bg-muted/40 px-3 py-2 font-mono text-xs whitespace-pre-wrap"
        >
          {loading && <span className="text-muted-foreground">Loading log…</span>}
          {error && <span className="text-destructive">{error}</span>}
          {!loading &&
            !error &&
            (log ? log : <span className="text-muted-foreground">No log output.</span>)}
        </div>
      )}
    </div>
  );
}
