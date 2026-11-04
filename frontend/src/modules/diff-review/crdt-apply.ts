/** Minimal CRDT (Y.Text) apply (spec 47). Writes a small, origin-tagged edit. */
import * as Y from "yjs";

import { minimalEdit } from "./hunks";
import type { DocumentBridge, TextSplice } from "./types";

export const AGENT_APPLY_ORIGIN = "agent-apply";

/**
 * Apply `target` content to `ytext` as a minimal single-region edit (common prefix +
 * suffix preserved) inside one Yjs transaction tagged with the agent origin — so
 * concurrent edits outside the changed region are preserved by the CRDT.
 */
export function applyTargetToYText(
  ytext: Y.Text,
  target: string,
  origin: unknown = AGENT_APPLY_ORIGIN,
): void {
  const current = ytext.toString();
  if (current === target) return;
  const edit = minimalEdit(current, target);
  const run = () => {
    if (edit.deleteLength > 0) ytext.delete(edit.start, edit.deleteLength);
    if (edit.insert) ytext.insert(edit.start, edit.insert);
  };
  if (ytext.doc) ytext.doc.transact(run, origin);
  else run();
}

export const SEARCH_REPLACE_ORIGIN = "search-replace";

/**
 * Writes `splices` into `ytext` in one transaction, last first, so each offset still means what it meant in the
 * text they were computed on. Each splice touches only its own range, so a collaborator's edit between two
 * matches survives (spec 122). The splices must not overlap.
 */
export function applySplicesToYText(
  ytext: Y.Text,
  splices: readonly TextSplice[],
  origin: unknown = SEARCH_REPLACE_ORIGIN,
): void {
  if (splices.length === 0) return;
  const ordered = [...splices].sort((a, b) => b.from - a.from);
  const run = () => {
    for (const splice of ordered) {
      if (splice.to > splice.from) ytext.delete(splice.from, splice.to - splice.from);
      if (splice.insert) ytext.insert(splice.from, splice.insert);
    }
  };
  if (ytext.doc) ytext.doc.transact(run, origin);
  else run();
}

/**
 * An in-process bridge over a set of Y.Docs keyed by path — used by tests and as the
 * building block for the editor's live bridge. `getText(path)` resolves the doc's
 * `content` Y.Text, creating a doc lazily from `seed` content.
 */
export function createYDocBridge(seed: Record<string, string> = {}): DocumentBridge & {
  getText: (path: string) => Y.Text;
  doc: (path: string) => Y.Doc;
} {
  const docs = new Map<string, Y.Doc>();
  const ensure = (path: string): Y.Doc => {
    let doc = docs.get(path);
    if (!doc) {
      doc = new Y.Doc();
      if (seed[path]) doc.getText("content").insert(0, seed[path]);
      docs.set(path, doc);
    }
    return doc;
  };
  return {
    getText: (path) => ensure(path).getText("content"),
    doc: (path) => ensure(path),
    async readContent(path) {
      return ensure(path).getText("content").toString();
    },
    async applyContent(path, target) {
      applyTargetToYText(ensure(path).getText("content"), target);
    },
  };
}
