/**
 * Pure BibTeX reader (spec 112): the key, type, title, author and year of each entry, in file order. Tolerant by
 * design: an entry that cannot be read is skipped, so a half-typed `.bib` keeps the completion working.
 */

export interface BibEntry {
  key: string;
  /** The entry type, lowercase: `article`, `book`… */
  type: string;
  title?: string;
  author?: string;
  year?: string;
}

/** Entries that hold no citable work: their bodies are skipped whole. */
const SKIPPED = new Set(["comment", "string", "preamble"]);
const ENTRY_START = /@([A-Za-z]+)\s*\{/g;

/** Index of the brace that closes the one at `open`, or -1. Escaped braces do not count. */
function closeOf(text: string, open: number): number {
  let depth = 0;
  for (let i = open; i < text.length; i++) {
    const c = text[i];
    if (c === "\\") i++;
    else if (c === "{") depth++;
    else if (c === "}" && --depth === 0) return i;
  }
  return -1;
}

/** The index of the quote that closes the string opened at `at`, or -1 when it is never closed. */
function quoteEnd(text: string, at: number): number {
  for (let i = at + 1; i < text.length; i++) {
    if (text[i] === "\\") i++;
    else if (text[i] === '"') return i;
  }
  return -1;
}

interface Piece {
  value: string;
  end: number;
}

/** A braced group, a quoted string or a bare word (a year, a macro) that starts at `at`. */
function readPiece(body: string, at: number): Piece | null {
  const c = body[at];
  if (c === "{" || c === '"') {
    const close = c === "{" ? closeOf(body, at) : quoteEnd(body, at);
    return close < 0 ? null : { value: body.slice(at + 1, close), end: close + 1 };
  }
  const word = /[^\s,{}()"#=]+/y;
  word.lastIndex = at;
  const match = word.exec(body);
  return match ? { value: match[0], end: at + match[0].length } : null;
}

/** A value, its pieces joined by `#` (`"Silva" # " and Souza"`). */
function readValue(body: string, at: number): Piece | null {
  const first = readPiece(body, at);
  if (!first) return null;
  let { value, end } = first;
  for (;;) {
    const hash = /\s*#\s*/y;
    hash.lastIndex = end;
    const joint = hash.exec(body);
    const next = joint ? readPiece(body, end + joint[0].length) : null;
    if (!next) return { value, end };
    value += next.value;
    end = next.end;
  }
}

/** The `name = value` pairs of an entry body, names lowercase. A malformed pair ends the list. */
function readFields(body: string): Map<string, string> {
  const fields = new Map<string, string>();
  let at = 0;
  for (;;) {
    const name = /\s*([A-Za-z][\w-]*)\s*=\s*/y;
    name.lastIndex = at;
    const head = name.exec(body);
    const value = head ? readValue(body, name.lastIndex) : null;
    if (!head || !value) return fields;
    fields.set(head[1].toLowerCase(), value.value);
    const comma = /\s*,?/y;
    comma.lastIndex = value.end;
    at = value.end + (comma.exec(body)?.[0].length ?? 0);
  }
}

/** Drops the one brace level that wraps the whole value (`{{Deep}}` reads `Deep`), collapsing whitespace. */
function clean(value: string | undefined): string | undefined {
  if (value === undefined) return undefined;
  let text = value.trim();
  if (text.startsWith("{") && closeOf(text, 0) === text.length - 1) text = text.slice(1, -1);
  const squashed = text.replace(/\s+/g, " ").trim();
  return squashed === "" ? undefined : squashed;
}

/** The entry whose `@type{` brace is at `open`, or null when its key is missing or the entry is unclosed. */
function parseEntry(text: string, type: string, open: number): BibEntry | null {
  const close = closeOf(text, open);
  if (close < 0) return null;
  const body = text.slice(open + 1, close);
  const comma = body.indexOf(",");
  const key = (comma < 0 ? body : body.slice(0, comma)).trim();
  if (key === "" || /[\s{}"]/.test(key)) return null;
  const fields = comma < 0 ? new Map<string, string>() : readFields(body.slice(comma + 1));
  return {
    key,
    type,
    title: clean(fields.get("title")),
    author: clean(fields.get("author")),
    year: clean(fields.get("year")),
  };
}

/** Every citable entry of a `.bib` text, in file order. Never throws. */
export function parseBib(text: string): BibEntry[] {
  const entries: BibEntry[] = [];
  const starts = new RegExp(ENTRY_START.source, "g");
  for (let match = starts.exec(text); match; match = starts.exec(text)) {
    const type = match[1].toLowerCase();
    const open = match.index + match[0].length - 1;
    const close = closeOf(text, open);
    if (close < 0) continue;
    const entry = SKIPPED.has(type) ? null : parseEntry(text, type, open);
    if (entry) entries.push(entry);
    starts.lastIndex = close + 1;
  }
  return entries;
}
