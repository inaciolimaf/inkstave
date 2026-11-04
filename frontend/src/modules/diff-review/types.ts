/** Diff-review domain types (spec 47), consuming the spec-43/44 proposal model. */

export type LineType = "ctx" | "add" | "del";

export interface HunkLine {
  type: LineType;
  text: string;
}

export interface DiffHunk {
  id: string;
  header: string;
  oldStart: number;
  oldLines: number;
  newStart: number;
  newLines: number;
  lines: HunkLine[];
}

export interface ProposedFileDiff {
  path: string;
  baseVersion: string;
  docId: string;
  hunks: DiffHunk[];
}

export interface DiffProposal {
  id: string;
  projectId: string;
  sessionId: string;
  /** The proposal's status; only `proposed` can still be reviewed (spec 110). */
  status: string;
  files: ProposedFileDiff[];
  createdAt: string; // mapped from wire createdAt
}

/** The editor-provided capability to read + write a document's live CRDT text. */
export interface DocumentBridge {
  /** Current live content of the document at `path`, or null if it can't be opened. */
  readContent(path: string): Promise<string | null>;
  /** Apply `target` content to the document's Y.Text as a minimal, origin-tagged edit. */
  applyContent(path: string, target: string): Promise<void>;
  /** Release any transient resources (open providers). */
  destroy?(): void;
}

/** One change to a document's text: `[from, to)` becomes `insert` (spec 122). */
export interface TextSplice {
  from: number;
  to: number;
  insert: string;
}

/** A bridge that can also compute edits on the live text and write them at once (spec 122: replace). */
export interface LiveTextBridge extends DocumentBridge {
  /**
   * Reads the live text at `path`, asks `edit` for splices on it, writes them in one transaction and resolves to the
   * new text, or `null` when the document cannot be opened. Nothing runs between the read and the write, so the
   * splices land on the text they were computed from. An error thrown by `edit` writes nothing.
   */
  transformContent(path: string, edit: (text: string) => TextSplice[]): Promise<string | null>;
  destroy(): void;
}
