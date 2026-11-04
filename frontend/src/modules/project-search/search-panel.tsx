/**
 * Search and replace across every document of the project (spec 122), the third tab of the file drawer. Replacing
 * all asks first, with the count taken over every match, not only the listed ones.
 */
import { useEffect, useRef, useState } from "react";
import { type TFunction } from "i18next";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";

import { SearchControls } from "./search-controls";
import { type MatchTarget, SearchResultsList } from "./search-results";
import type { ProjectSearchState } from "./use-project-search";

export type SearchStatus = "loading" | "ready" | "limited";

export interface SearchPanelProps {
  state: ProjectSearchState;
  status: SearchStatus;
  onOpen: (target: MatchTarget) => void;
  /** Changes each time the writer asks for the search (Ctrl+Shift+F): the query field takes the focus. */
  focusKey: number;
}

/** What the panel says above the results: the count, or why there is none. */
function summaryLines(state: ProjectSearchState, status: SearchStatus, t: TFunction<"search">): string[] {
  const { results } = state;
  const lines: string[] = status === "limited" ? [t("limited")] : [];
  if (state.error || state.query === "") return lines;
  if (results.total > 0) {
    const files = t("files", { count: results.files.length });
    lines.push(t("summary", { results: t("results", { count: results.total }), files }));
    if (results.truncated) lines.push(t("truncated", { count: results.total }));
  } else if (status === "loading") lines.push(t("loading"));
  else if (state.settled) lines.push(t("none"));
  return lines;
}

function Summary({ state, status }: { state: ProjectSearchState; status: SearchStatus }) {
  const { t } = useTranslation("search");
  const lines = summaryLines(state, status, t);
  if (state.query === "" && !state.error) lines.push(t("idle"));
  return (
    <div role="status" className="space-y-0.5 px-2 py-1.5 text-small text-muted-foreground">
      {state.error && <p className="text-destructive">{t("invalid", { message: state.error })}</p>}
      {lines.map((line) => (
        <p key={line}>{line}</p>
      ))}
    </div>
  );
}

function ReplaceAll({ state }: { state: ProjectSearchState }) {
  const { t } = useTranslation("search");
  const [confirm, setConfirm] = useState<{ matches: number; files: number } | null>(null);
  useEffect(() => setConfirm(null), [state.results]);
  if (!state.canReplace || state.results.total === 0) return null;
  if (state.busy) return <p className="px-2 pb-2 text-small text-muted-foreground">{t("replacing")}</p>;
  if (!confirm) {
    return (
      <div className="px-2 pb-2">
        <Button size="sm" variant="outline" className="w-full" onClick={() => setConfirm(state.totals())}>
          {t("replaceAll")}
        </Button>
      </div>
    );
  }
  const counts = {
    matches: t("matches", { count: confirm.matches }),
    files: t("files", { count: confirm.files }),
  };
  return (
    <div role="alertdialog" aria-label={t("replaceAll")} className="space-y-1.5 px-2 pb-2 text-small">
      <p>{t("confirm", counts)}</p>
      <div className="flex gap-1.5">
        <Button
          size="sm"
          className="flex-1"
          autoFocus
          onClick={() => {
            setConfirm(null);
            void state.replaceAll();
          }}
        >
          {t("confirmAction")}
        </Button>
        <Button size="sm" variant="ghost" className="flex-1" onClick={() => setConfirm(null)}>
          {t("cancel")}
        </Button>
      </div>
    </div>
  );
}

export function SearchPanel({ state, status, onOpen, focusKey }: SearchPanelProps) {
  const { t } = useTranslation("search");
  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (focusKey === 0) return;
    // After the drawer has taken the focus for itself on opening.
    const frame = window.requestAnimationFrame(() => inputRef.current?.select());
    return () => window.cancelAnimationFrame(frame);
  }, [focusKey]);

  return (
    <section aria-label={t("title")} className="flex h-full flex-col">
      <SearchControls state={state} inputRef={inputRef} />
      <Summary state={state} status={status} />
      <ReplaceAll state={state} />
      <div className="min-h-0 flex-1 overflow-auto">
        <SearchResultsList
          files={state.results.files}
          busy={state.busy}
          onOpen={onOpen}
          onReplace={state.canReplace ? (file, match) => void state.replaceOne(file, match) : undefined}
        />
      </div>
      {!state.canReplace && state.results.total > 0 && (
        <p className="border-t border-control-edge px-2 py-1.5 text-small text-muted-foreground">
          {t("viewOnly")}
        </p>
      )}
    </section>
  );
}
