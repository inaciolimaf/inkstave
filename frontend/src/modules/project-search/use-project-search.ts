/** The state of the search panel (spec 122): the query, its options, the results and the replace actions. */
import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { type TextMatch, findMatches } from "./find";
import { type Matcher, type SearchOptions, DEFAULT_OPTIONS, buildMatcher } from "./matcher";
import {
  type FileRef,
  type ReplaceAllOutcome,
  type TextWriter,
  StaleMatchError,
  replaceInFiles,
  replaceMatch,
} from "./replace-actions";
import {
  type FileResult,
  type SearchResults,
  type SourceText,
  NO_RESULTS,
  searchSources,
} from "./search-project";

/** How long typing settles before the project is searched again. */
export const SEARCH_DEBOUNCE_MS = 200;

export interface ProjectSearchOptions {
  sources: readonly SourceText[];
  /** Opens a writer for one replace; it is destroyed when the replace ends. Absent for a viewer. */
  openWriter?: () => TextWriter & { destroy?: () => void };
  /** A document's new text after a replace, so the results follow it at once. */
  onWritten: (docId: string, text: string) => void;
}

function useDebounced<T>(value: T, ms: number): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setSettled(value), ms);
    return () => window.clearTimeout(timer);
  }, [value, ms]);
  return settled;
}

/** The documents that hold at least one match, every one of them, past the list's cap too. */
function filesWithMatches(sources: readonly SourceText[], pattern: RegExp): FileRef[] {
  return sources
    .filter((source) => findMatches(source.text, pattern, 1).length > 0)
    .map((source) => ({ docId: source.id, path: source.path }));
}

/** Every match of the project, uncapped, for the confirmation of "Replace all". */
function countMatches(sources: readonly SourceText[], pattern: RegExp): { matches: number; files: number } {
  let matches = 0;
  let files = 0;
  for (const source of sources) {
    const found = findMatches(source.text, pattern).length;
    matches += found;
    if (found > 0) files += 1;
  }
  return { matches, files };
}

export function useProjectSearch({ sources, openWriter, onWritten }: ProjectSearchOptions) {
  const { t } = useTranslation("search");
  const [query, setQuery] = useState("");
  const [replacement, setReplacement] = useState("");
  const [options, setOptions] = useState<SearchOptions>(DEFAULT_OPTIONS);
  const [busy, setBusy] = useState(false);
  const settledQuery = useDebounced(query, SEARCH_DEBOUNCE_MS);

  const matcher: Matcher | null = useMemo(() => buildMatcher(settledQuery, options), [settledQuery, options]);
  const pattern = matcher?.ok ? matcher.pattern : null;
  const results: SearchResults = useMemo(
    () => (pattern ? searchSources(sources, pattern) : NO_RESULTS),
    [sources, pattern],
  );

  const run = useCallback(
    async <T>(work: (writer: TextWriter) => Promise<T>): Promise<T | undefined> => {
      if (!openWriter) return undefined;
      const writer = openWriter();
      setBusy(true);
      try {
        return await work(writer);
      } finally {
        writer.destroy?.();
        setBusy(false);
      }
    },
    [openWriter],
  );

  const replaceOne = useCallback(
    async (file: FileResult, match: TextMatch) => {
      if (!pattern) return;
      try {
        const text = await run((writer) =>
          replaceMatch(writer, file, match, { pattern, replacement, regex: options.regex }),
        );
        if (text) onWritten(file.docId, text);
      } catch (error) {
        toast.error(error instanceof StaleMatchError ? t("stale") : t("failed", { paths: file.path }));
      }
    },
    [pattern, replacement, options.regex, run, onWritten, t],
  );

  const replaceAll = useCallback(async () => {
    if (!pattern) return;
    const targets = filesWithMatches(sources, pattern);
    const outcome: ReplaceAllOutcome | undefined = await run((writer) =>
      replaceInFiles(writer, targets, { pattern, replacement, regex: options.regex }, onWritten),
    );
    if (!outcome) return;
    const counts = {
      matches: t("matches", { count: outcome.replaced }),
      files: t("files", { count: outcome.files }),
    };
    if (outcome.replaced > 0) toast.success(t("done", counts));
    if (outcome.failed.length > 0) toast.error(t("failed", { paths: outcome.failed.join(", ") }));
  }, [pattern, sources, replacement, options.regex, run, onWritten, t]);

  const totals = useCallback(() => (pattern ? countMatches(sources, pattern) : null), [pattern, sources]);

  return {
    query,
    setQuery,
    replacement,
    setReplacement,
    options,
    setOptions,
    /** The query has settled, so `results` answer what is in the box. */
    settled: query === settledQuery,
    error: matcher && !matcher.ok ? matcher.error : null,
    results,
    busy,
    canReplace: openWriter !== undefined,
    replaceOne,
    replaceAll,
    totals,
  };
}

export type ProjectSearchState = ReturnType<typeof useProjectSearch>;
