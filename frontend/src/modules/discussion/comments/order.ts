/**
 * What the comments panel lists, and in which order (spec 118): the open document's threads in text
 * order, then its detached threads, then the threads of other documents by file name and age.
 */
import type { ResolvedRange } from "./anchors";
import type { CommentThread } from "./api";

export type ThreadStatusFilter = "open" | "resolved" | "all";
export type ThreadScope = "file" | "all";

export interface ThreadRow {
  thread: CommentThread;
  current: boolean;
  /** Where the thread is now, for threads of the open document; null when detached. */
  range: ResolvedRange | null;
}

export function matchesStatus(thread: CommentThread, filter: ThreadStatusFilter): boolean {
  if (filter === "open") return thread.resolved_at === null;
  if (filter === "resolved") return thread.resolved_at !== null;
  return true;
}

function rank(row: ThreadRow): number {
  if (!row.current) return 2;
  return row.range ? 0 : 1;
}

/**
 * The rows to show. `ranges` holds the current range of each thread of the open document; a thread
 * missing from it counts as detached.
 */
export function orderThreads(
  threads: CommentThread[],
  options: {
    currentDocumentId: string | null;
    ranges: Map<string, ResolvedRange | null>;
    fileName: (documentId: string) => string;
    filter: ThreadStatusFilter;
    scope: ThreadScope;
  },
): ThreadRow[] {
  const rows: ThreadRow[] = threads
    .filter((thread) => matchesStatus(thread, options.filter))
    .map((thread) => {
      const current = thread.document_id === options.currentDocumentId;
      const range = current ? (options.ranges.get(thread.id) ?? null) : null;
      return { thread, current, range };
    })
    .filter((row) => options.scope === "all" || row.current);

  return rows.sort((a, b) => {
    const byRank = rank(a) - rank(b);
    if (byRank !== 0) return byRank;
    if (a.range && b.range) return a.range.from - b.range.from;
    if (!a.current && !b.current) {
      const byName = options
        .fileName(a.thread.document_id)
        .localeCompare(options.fileName(b.thread.document_id));
      if (byName !== 0) return byName;
    }
    return a.thread.created_at.localeCompare(b.thread.created_at);
  });
}
