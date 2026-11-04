/** The matches, grouped by file (spec 122). A row opens its match; its button replaces only that one. */
import { Replace } from "lucide-react";
import { useTranslation } from "react-i18next";

import type { TextMatch } from "./find";
import { previewOf } from "./find";
import type { FileResult } from "./search-project";

export interface MatchTarget {
  path: string;
  line: number;
  column: number;
  length: number;
}

function MatchRow({
  path,
  match,
  onOpen,
  onReplace,
  busy,
}: {
  path: string;
  match: TextMatch;
  onOpen: () => void;
  onReplace?: () => void;
  busy: boolean;
}) {
  const { t } = useTranslation("search");
  const preview = previewOf(match);
  return (
    <li className="group flex items-stretch">
      <button
        type="button"
        onClick={onOpen}
        aria-label={t("matchLabel", { path, line: match.line, text: match.lineText.trim() })}
        title={t("line", { line: match.line })}
        className="flex min-w-0 flex-1 items-baseline gap-2 px-2 py-0.5 text-left hover:bg-accent"
      >
        <span className="w-8 shrink-0 text-right font-mono text-muted-foreground">{match.line}</span>
        <span className="truncate font-mono">
          {preview.before}
          <mark className="rounded-sm bg-warning-soft text-foreground">{preview.match}</mark>
          {preview.after}
        </span>
      </button>
      {onReplace && (
        <button
          type="button"
          disabled={busy}
          onClick={onReplace}
          aria-label={t("replaceOneAt", { path, line: match.line })}
          title={t("replaceOne")}
          className="shrink-0 px-1.5 text-muted-foreground opacity-60 hover:bg-accent hover:text-foreground focus-visible:opacity-100 disabled:opacity-30 group-hover:opacity-100"
        >
          <Replace className="size-3.5" aria-hidden />
        </button>
      )}
    </li>
  );
}

export function SearchResultsList({
  files,
  onOpen,
  onReplace,
  busy,
}: {
  files: readonly FileResult[];
  onOpen: (target: MatchTarget) => void;
  onReplace?: (file: FileResult, match: TextMatch) => void;
  busy: boolean;
}) {
  const { t } = useTranslation("search");
  return (
    <ul className="py-1 text-small">
      {files.map((file) => (
        <li key={file.docId} className="pb-1">
          <div className="flex items-baseline justify-between gap-2 px-2 py-1">
            <span className="truncate font-medium" title={file.path}>
              {file.path}
            </span>
            <span className="shrink-0 text-muted-foreground">
              {t("matches", { count: file.matches.length })}
            </span>
          </div>
          <ul>
            {file.matches.map((match) => (
              <MatchRow
                key={match.from}
                path={file.path}
                match={match}
                busy={busy}
                onOpen={() =>
                  onOpen({
                    path: file.path,
                    line: match.line,
                    column: match.column,
                    length: match.text.length,
                  })
                }
                onReplace={onReplace ? () => onReplace(file, match) : undefined}
              />
            ))}
          </ul>
        </li>
      ))}
    </ul>
  );
}
