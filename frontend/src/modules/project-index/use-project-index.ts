import type { EditorView } from "@codemirror/view";
import { type UseQueryResult, useQueries, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef } from "react";

import type { TreeNode } from "@/modules/file-tree";

import { fetchDocumentText } from "./api";
import {
  type BibRef,
  type DocText,
  type LabelRef,
  type ProjectFile,
  MAX_INDEXED_DOCUMENTS,
  buildIndex,
  collectBib,
  collectLabels,
  collectTexts,
  listDocuments,
  listFiles,
  withLiveText,
} from "./build-index";
import { type ResolvedItem, resolveIncludes } from "./resolve-includes";
import { useLiveSource } from "./use-live-source";

/** How long a fetched copy is trusted before a focus of the window fetches it again (someone may have saved). */
export const INDEX_STALE_MS = 30_000;

export type IndexStatus = "loading" | "ready" | "limited";

export interface ProjectIndex {
  /** Sections and labels in document order, following the includes from the main document. */
  entries: ResolvedItem[];
  /** `limited`: the project is over the caps, so only the open file is in `entries`. */
  status: IndexStatus;
  /** Live 1-based cursor line in the open file. */
  cursorLine: number;
  /** Every label of the indexed files (spec 112: `\ref` targets). */
  labels: LabelRef[];
  /** Every `.bib` entry of the project (spec 112: `\cite` keys). */
  bib: BibRef[];
  /** Every document and file of the tree (spec 112: `\input` and `\includegraphics` paths). */
  files: ProjectFile[];
  /** The text of every indexed document, the open one live (spec 122: the project search). */
  texts: DocText[];
  /** Records a document's new text, written by this page, so the index does not wait for a refetch. */
  setDocText: (docId: string, text: string) => void;
}

/**
 * What the hook needs from the queries. A module-level function, so TanStack keeps the result between renders and
 * the index is not parsed again on each render.
 */
function summarize(results: UseQueryResult<string>[]) {
  return {
    texts: results.map((result) => result.data),
    pending: results.some((result) => result.fetchStatus === "fetching"),
  };
}

export function indexKey(projectId: string, docId: string) {
  return ["project-index", projectId, docId] as const;
}

interface ProjectIndexOptions {
  projectId: string;
  root: TreeNode | undefined;
  /** The document the outline starts from: the one compile uses. */
  mainDocId: string | null;
  openDocId: string | null;
  /** The editor showing the open file. */
  view: EditorView | null;
}

/**
 * The project index (spec 111): fetches every document once, keeps the open file live, and resolves the includes.
 * The open file is read from the editor, so it is never behind what the writer typed. Documents are refetched when
 * the window regains focus, and the one just left is written back with its latest text.
 */
export function useProjectIndex({
  projectId,
  root,
  mainDocId,
  openDocId,
  view,
}: ProjectIndexOptions): ProjectIndex {
  const queryClient = useQueryClient();
  const snapshots = useRef(new Map<string, string>());
  const live = useLiveSource(view, openDocId, snapshots);
  const docs = useMemo(() => listDocuments(root), [root]);
  const overCap = docs.length > MAX_INDEXED_DOCUMENTS;

  const { texts, pending } = useQueries({
    queries: docs.map((doc) => ({
      queryKey: indexKey(projectId, doc.id),
      queryFn: () => fetchDocumentText(projectId, doc.id),
      staleTime: INDEX_STALE_MS,
      enabled: !overCap || doc.id === openDocId,
    })),
    combine: summarize,
  });

  const base = useMemo(() => buildIndex(docs, texts, openDocId), [docs, texts, openDocId]);
  const index = useMemo(
    () => withLiveText(base.index, docs, openDocId, live.text),
    [base, docs, openDocId, live.text],
  );
  const entries = useMemo(() => resolveIncludes(mainDocId, index), [mainDocId, index]);
  const labels = useMemo(() => collectLabels(index), [index]);
  const bib = useMemo(
    () => collectBib(docs, texts, openDocId, live.text),
    [docs, texts, openDocId, live.text],
  );
  const files = useMemo(() => listFiles(root), [root]);
  const docTexts = useMemo(
    () => collectTexts(docs, texts, openDocId, live.text, base.limited),
    [docs, texts, openDocId, live.text, base.limited],
  );
  const setDocText = useCallback(
    (docId: string, text: string) => {
      if (docId === openDocId) snapshots.current.set(docId, text);
      queryClient.setQueryData(indexKey(projectId, docId), text);
    },
    [openDocId, projectId, queryClient],
  );

  const previous = useRef(openDocId);
  useEffect(() => {
    const left = previous.current;
    previous.current = openDocId;
    if (left === null || left === openDocId) return;
    const text = snapshots.current.get(left);
    if (text !== undefined) queryClient.setQueryData(indexKey(projectId, left), text);
  }, [openDocId, projectId, queryClient]);

  const status: IndexStatus = base.limited
    ? "limited"
    : pending && entries.length === 0
      ? "loading"
      : "ready";
  return { entries, status, cursorLine: live.line, labels, bib, files, texts: docTexts, setDocText };
}
