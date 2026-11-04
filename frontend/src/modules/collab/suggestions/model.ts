/**
 * The suggestions of a document (spec 119): the records in `Y.Map("suggestions")`, keyed by suggestion id, and
 * their positions in the text. Positions are Yjs relative positions, base64 encoded, so a record follows its
 * text through every edit, on every peer. Nothing here touches the text itself.
 */
import * as Y from "yjs";

export const SUGGESTIONS_KEY = "suggestions";
/** A suggested deletion keeps at most this many characters (spec 119 §5.2). */
export const SUGGESTION_TEXT_MAX_CHARS = 100_000;
/** A deleted text longer than this is folded in the text (spec 119 §3). */
export const SUGGESTION_FOLD_CHARS = 40;

export interface SuggestionAuthor {
  id: string;
  name: string;
}

export interface InsertionFields {
  kind: "insert";
  author_id: string;
  author_name: string;
  created_at: string;
  /** The first character of the insertion (assoc 0). */
  start: string;
  /** The position after the last character (assoc -1). */
  end: string;
}

export interface DeletionFields {
  kind: "delete";
  author_id: string;
  author_name: string;
  created_at: string;
  /** Where the removed text was (assoc 0). */
  at: string;
  /** The removed text. */
  text: string;
}

export type SuggestionFields = InsertionFields | DeletionFields;
export type SuggestionMap = Y.Map<SuggestionFields>;

export type Suggestion = SuggestionFields & { id: string };

export interface TextRange {
  from: number;
  to: number;
}

/** A suggestion with its place in the text now; `range` is null when the place is gone. */
export interface PlacedSuggestion {
  suggestion: Suggestion;
  range: TextRange | null;
}

/** An insertion of the caller, as the planner needs it: its current range and when it was made. */
export interface OwnInsertion extends TextRange {
  id: string;
  createdAt: string;
}

/** The map that holds the suggestions of a document. */
export function suggestionsOf(ytext: Y.Text): SuggestionMap | null {
  const doc = ytext.doc;
  return doc ? (doc.getMap(SUGGESTIONS_KEY) as SuggestionMap) : null;
}

/** A time-ordered UUID (version 7): 48 bits of milliseconds, then random bits. */
export function newSuggestionId(now: number = Date.now()): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  let millis = now;
  for (let i = 5; i >= 0; i--) {
    bytes[i] = millis % 256;
    millis = Math.floor(millis / 256);
  }
  bytes[6] = (bytes[6] & 0x0f) | 0x70;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

function toBase64(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

function fromBase64(value: string): Uint8Array {
  return Uint8Array.from(atob(value), (char) => char.charCodeAt(0));
}

/** The relative position of an index in the text, as a base64 string. */
export function encodePosition(ytext: Y.Text, index: number, assoc: number): string {
  return toBase64(Y.encodeRelativePosition(Y.createRelativePositionFromTypeIndex(ytext, index, assoc)));
}

/** The index a stored position points at now, or null when its text is gone or the value is malformed. */
export function resolvePosition(ytext: Y.Text, encoded: string): number | null {
  const doc = ytext.doc;
  if (!doc) return null;
  try {
    const absolute = Y.createAbsolutePositionFromRelativePosition(
      Y.decodeRelativePosition(fromBase64(encoded)),
      doc,
    );
    return absolute && absolute.type === ytext ? absolute.index : null;
  } catch {
    return null;
  }
}

/**
 * The range a suggestion covers now. A deletion has an empty range at its place; an insertion has none once
 * its text is gone, and then it is stale.
 */
export function resolveSuggestion(ytext: Y.Text, suggestion: SuggestionFields): TextRange | null {
  if (suggestion.kind === "delete") {
    const at = resolvePosition(ytext, suggestion.at);
    return at === null ? null : { from: at, to: at };
  }
  const from = resolvePosition(ytext, suggestion.start);
  const to = resolvePosition(ytext, suggestion.end);
  // An insertion whose text a plain edit deleted in full has nothing left to accept: its range is empty.
  if (from === null || to === null || to <= from) return null;
  return { from, to };
}

function isSuggestionFields(value: unknown): value is SuggestionFields {
  if (typeof value !== "object" || value === null) return false;
  const kind = (value as { kind?: unknown }).kind;
  return kind === "insert" || kind === "delete";
}

/** Every suggestion of the document, in text order; a suggestion whose place is gone comes last. */
export function readSuggestions(ytext: Y.Text, map: SuggestionMap): PlacedSuggestion[] {
  const placed: PlacedSuggestion[] = [];
  map.forEach((value, id) => {
    if (!isSuggestionFields(value)) return;
    const range = resolveSuggestion(ytext, value);
    placed.push({ suggestion: { ...value, id }, range });
  });
  return placed.sort((a, b) => {
    if (a.range === null || b.range === null) return a.range === null ? (b.range === null ? 0 : 1) : -1;
    return a.range.from - b.range.from || a.suggestion.created_at.localeCompare(b.suggestion.created_at);
  });
}

/** The insertions of one author, with their current ranges: what the planner may grow, shrink or merge. */
export function ownInsertions(ytext: Y.Text, map: SuggestionMap, authorId: string): OwnInsertion[] {
  const own: OwnInsertion[] = [];
  for (const { suggestion, range } of readSuggestions(ytext, map)) {
    if (suggestion.kind !== "insert" || suggestion.author_id !== authorId || range === null) continue;
    own.push({ id: suggestion.id, from: range.from, to: range.to, createdAt: suggestion.created_at });
  }
  return own;
}
