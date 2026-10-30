import { Check, Copy } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import i18n from "@/i18n/config";

import type { CompileStatus } from "./types";

function statusLine(meta: CompileStatus | null): string | null {
  if (!meta) return null;
  const parts: string[] = [meta.status];
  if (meta.duration_ms != null) parts.push(`${(meta.duration_ms / 1000).toFixed(1)}s`);
  if (meta.exit_code != null) parts.push(i18n.t("preview:status.exit", { code: meta.exit_code }));
  return parts.join(" · ");
}

/**
 * Raw compile-log viewer (spec 24, §5.3.6). Visibility is owned by the shared
 * compile-output dock (see PreviewPane): the panel renders its status line, a
 * copy button and the log region only while `expanded`. The log is lazy-fetched
 * the first time the panel is shown.
 */
export function LogPanel({
  expanded,
  log,
  loading,
  error,
  onFetch,
  meta,
}: {
  expanded: boolean;
  log: string | null;
  loading: boolean;
  error: string | null;
  onFetch: () => void;
  meta: CompileStatus | null;
}) {
  const { t } = useTranslation(["preview", "common"]);
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

  if (!expanded) return null;

  const line = statusLine(meta);

  return (
    <div className="flex flex-col">
      {(line || log != null) && (
        <div className="flex items-center gap-2 border-b px-3 py-1.5">
          {line && <span className="truncate text-xs text-muted-foreground">{line}</span>}
          {log != null && (
            <Button
              size="sm"
              variant="ghost"
              className="ml-auto h-7"
              onClick={copy}
              aria-label={t("log.copyToClipboard")}
            >
              {copied ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
              {copied ? t("common:action.copied") : t("common:action.copy")}
            </Button>
          )}
        </div>
      )}
      <div
        id="compile-log-region"
        role="region"
        aria-label={t("log.compileLog")}
        tabIndex={0}
        className="max-h-48 overflow-auto bg-muted/40 px-3 py-2 font-mono text-xs whitespace-pre-wrap"
      >
        {loading && <span className="text-muted-foreground">{t("log.loadingLog")}</span>}
        {error && <span className="text-destructive">{error}</span>}
        {!loading &&
          !error &&
          (log ? log : <span className="text-muted-foreground">{t("log.noLogOutput")}</span>)}
      </div>
    </div>
  );
}
