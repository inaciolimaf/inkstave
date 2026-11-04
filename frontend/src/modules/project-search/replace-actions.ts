/**
 * Writing a replacement (spec 122). Each file is read and written in one step on its live collaborative text, so
 * the edit applies to what the document holds now, not to the copy the search ran on.
 */
import { type TextMatch, findMatches } from "./find";
import { type TextEdit, relocate, replacementEdits } from "./replace";
import type { FileResult } from "./search-project";

/** A document to write: its id, for the index, and its path, for the writer. */
export interface FileRef {
  docId: string;
  path: string;
}

/** The editor's way to change a document's live text. The editor builds it over the collaboration channel. */
export interface TextWriter {
  /**
   * Reads the live text of `path`, asks `edit` for the changes, and writes them in one transaction. Resolves to
   * the new text, or `null` when the document cannot be opened. An error thrown by `edit` writes nothing.
   */
  transformContent(path: string, edit: (text: string) => TextEdit[]): Promise<string | null>;
}

export interface ReplaceQuery {
  pattern: RegExp;
  replacement: string;
  regex: boolean;
}

/** The match is gone from the document, or its line changed, since the search ran. */
export class StaleMatchError extends Error {
  constructor() {
    super("The match changed since the search ran.");
    this.name = "StaleMatchError";
  }
}

/** Replaces one match. Throws `StaleMatchError` when it is no longer where the writer saw it. */
export async function replaceMatch(
  writer: TextWriter,
  file: FileResult,
  match: TextMatch,
  query: ReplaceQuery,
): Promise<string | null> {
  return writer.transformContent(file.path, (text) => {
    const current = relocate(findMatches(text, query.pattern), match, file.matches);
    if (!current) throw new StaleMatchError();
    return replacementEdits([current], query.replacement, query.regex);
  });
}

export interface ReplaceAllOutcome {
  /** Matches replaced, counted on the live texts. */
  replaced: number;
  /** Files changed. */
  files: number;
  /** Paths that could not be opened or written. */
  failed: string[];
}

/**
 * Replaces every match in `files` as each file reads now, the ones the result cap left out of the list included. Files are
 * written one after the other; one that fails is reported and the others still change. `onWritten` gets each new
 * text, so the search can show it at once.
 */
export async function replaceInFiles(
  writer: TextWriter,
  files: readonly FileRef[],
  query: ReplaceQuery,
  onWritten: (docId: string, text: string) => void,
): Promise<ReplaceAllOutcome> {
  const outcome: ReplaceAllOutcome = { replaced: 0, files: 0, failed: [] };
  for (const file of files) {
    let count = 0;
    try {
      const text = await writer.transformContent(file.path, (current) => {
        const edits = replacementEdits(findMatches(current, query.pattern), query.replacement, query.regex);
        count = edits.length;
        return edits;
      });
      if (text === null) throw new Error(`Cannot open ${file.path}`);
      onWritten(file.docId, text);
      outcome.replaced += count;
      if (count > 0) outcome.files += 1;
    } catch {
      outcome.failed.push(file.path);
    }
  }
  return outcome;
}
