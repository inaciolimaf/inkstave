/**
 * Assembles the index from the file tree and the fetched texts (spec 111). Past the caps the project is too
 * big to index in full, so only the open file stays in it.
 */
import type { TreeNode } from "@/modules/file-tree";

import { type IndexedDoc } from "./resolve-includes";
import { parseStructure } from "./parse-structure";

export const MAX_INDEXED_DOCUMENTS = 200;
/** Characters, a close enough proxy for the 2 MB of text the spec allows. */
export const MAX_INDEXED_CHARS = 2 * 1024 * 1024;

export interface DocRef {
  id: string;
  path: string;
}

export interface BuiltIndex {
  index: Map<string, IndexedDoc>;
  limited: boolean;
}

/** Every document of the tree, in tree order. */
export function listDocuments(root: TreeNode | undefined): DocRef[] {
  if (!root) return [];
  const docs: DocRef[] = [];
  const queue = [root];
  for (const node of queue) {
    if (node.type === "doc") docs.push({ id: node.id, path: node.path });
    queue.push(...node.children);
  }
  return docs;
}

/** Parses each fetched text. `texts[i]` belongs to `docs[i]`; `undefined` means not fetched or unreadable. */
export function buildIndex(
  docs: readonly DocRef[],
  texts: readonly (string | undefined)[],
  openDocId: string | null,
): BuiltIndex {
  const total = texts.reduce<number>((sum, text) => sum + (text?.length ?? 0), 0);
  const limited = docs.length > MAX_INDEXED_DOCUMENTS || total > MAX_INDEXED_CHARS;
  const index = new Map<string, IndexedDoc>();
  docs.forEach((doc, i) => {
    if (limited && doc.id !== openDocId) return;
    const text = texts[i];
    if (text !== undefined) index.set(doc.id, { ...doc, items: parseStructure(text) });
  });
  return { index, limited };
}

/** The open file, parsed from its live text (which is newer than any fetched copy). */
export function withLiveText(
  base: ReadonlyMap<string, IndexedDoc>,
  docs: readonly DocRef[],
  openDocId: string | null,
  liveText: string | null,
): Map<string, IndexedDoc> {
  const index = new Map(base);
  const open = docs.find((doc) => doc.id === openDocId);
  if (open && liveText !== null) index.set(open.id, { ...open, items: parseStructure(liveText) });
  return index;
}
