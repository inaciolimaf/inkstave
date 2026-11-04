/**
 * Assembles the index from the file tree and the fetched texts (spec 111). Past the caps the project is too
 * big to index in full, so only the open file stays in it.
 */
import type { TreeNode } from "@/modules/file-tree";

import { type BibEntry, parseBib } from "./parse-bib";
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

/** A document's text, for the project search (spec 122). */
export interface DocText {
  id: string;
  path: string;
  text: string;
}

/**
 * Every fetched document with its text, the open one live. Past the caps only the open file is searched, as
 * only it is indexed.
 */
export function collectTexts(
  docs: readonly DocRef[],
  texts: readonly (string | undefined)[],
  openDocId: string | null,
  liveText: string | null,
  limited: boolean,
): DocText[] {
  const out: DocText[] = [];
  docs.forEach((doc, i) => {
    if (limited && doc.id !== openDocId) return;
    const text = doc.id === openDocId && liveText !== null ? liveText : texts[i];
    if (text !== undefined) out.push({ ...doc, text });
  });
  return out;
}

/** A project file as completion sees it: a text document or a binary file (images, PDFs). */
export interface ProjectFile {
  path: string;
  type: "doc" | "file";
}

/** Every document and file of the tree, folders and the root left out. */
export function listFiles(root: TreeNode | undefined): ProjectFile[] {
  if (!root) return [];
  const files: ProjectFile[] = [];
  const queue = [root];
  for (const node of queue) {
    if (node.type !== "folder" && !node.isRoot) files.push({ path: node.path, type: node.type });
    queue.push(...node.children);
  }
  return files;
}

/** A bibliography entry with the `.bib` file it comes from; `alsoIn` lists the other files that define the key. */
export interface BibRef extends BibEntry {
  path: string;
  alsoIn?: string[];
}

/** Every `.bib` entry of the project. A key appears once: the first file that defines it wins (spec 112). */
export function collectBib(
  docs: readonly DocRef[],
  texts: readonly (string | undefined)[],
  openDocId: string | null,
  liveText: string | null,
): BibRef[] {
  const refs = new Map<string, BibRef>();
  docs.forEach((doc, i) => {
    if (!doc.path.toLowerCase().endsWith(".bib")) return;
    const text = doc.id === openDocId && liveText !== null ? liveText : texts[i];
    if (text === undefined) return;
    for (const entry of parseBib(text)) addBibEntry(refs, entry, doc.path);
  });
  return [...refs.values()];
}

function addBibEntry(refs: Map<string, BibRef>, entry: BibEntry, path: string): void {
  const first = refs.get(entry.key);
  if (!first) {
    refs.set(entry.key, { ...entry, path });
  } else if (first.path !== path && !first.alsoIn?.includes(path)) {
    first.alsoIn = [...(first.alsoIn ?? []), path];
  }
}

/** A `\label` of the project, with the file it is in and the section it falls under. */
export interface LabelRef {
  name: string;
  docId: string;
  path: string;
  /** The title of the last sectioning command before the label in its file. */
  section?: string;
  line: number;
}

/** Every label of every indexed file, in file order within each file. */
export function collectLabels(docs: ReadonlyMap<string, IndexedDoc>): LabelRef[] {
  const labels: LabelRef[] = [];
  for (const doc of docs.values()) {
    let section: string | undefined;
    for (const item of doc.items) {
      if (item.kind === "section") section = item.title;
      else if (item.kind === "label" && item.title) {
        labels.push({ name: item.title, docId: doc.id, path: doc.path, section, line: item.line });
      }
    }
  }
  return labels;
}
