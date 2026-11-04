/** Turns what the writer typed in the search box into a regular expression (spec 122). Pure, no DOM. */

export interface SearchOptions {
  caseSensitive: boolean;
  wholeWord: boolean;
  /** The query is a JavaScript regular expression, and `$1`, `$&`, `$<name>` work in the replacement. */
  regex: boolean;
}

export const DEFAULT_OPTIONS: SearchOptions = { caseSensitive: false, wholeWord: false, regex: false };

export type Matcher = { ok: true; pattern: RegExp } | { ok: false; error: string };

/** Escapes every character a regular expression gives a meaning to. Each escape is valid under the `u` flag. */
export function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** A word character for "whole word": a letter or digit of any script, or `_`, so `\section` ends before `{`. */
const WORD_UNICODE = "[\\p{L}\\p{N}_]";
const WORD_ASCII = "\\w";

function wrapWord(source: string, word: string): string {
  return `(?<!${word})(?:${source})(?!${word})`;
}

function compile(source: string, options: SearchOptions, unicode: boolean): RegExp {
  const body = options.wholeWord ? wrapWord(source, unicode ? WORD_UNICODE : WORD_ASCII) : source;
  const flags = `g${options.regex ? "m" : ""}${options.caseSensitive ? "" : "i"}${unicode ? "u" : ""}`;
  return new RegExp(body, flags);
}

/**
 * The pattern for a query, or `null` for an empty one. A regular expression is tried with the `u` flag first, so
 * `\p{L}` and astral characters work, and again without it, so a pattern written for the older syntax (`\-`)
 * still runs. Only a pattern that fails both ways is an error.
 */
export function buildMatcher(query: string, options: SearchOptions): Matcher | null {
  if (query === "") return null;
  const source = options.regex ? query : escapeRegExp(query);
  try {
    return { ok: true, pattern: compile(source, options, true) };
  } catch (unicodeError) {
    if (!options.regex) throw unicodeError;
    try {
      return { ok: true, pattern: compile(source, options, false) };
    } catch (error) {
      return { ok: false, error: error instanceof Error ? error.message : String(error) };
    }
  }
}
