/** The quote kept with a thread: at most 500 characters, cut on a character boundary (spec 118). */
export const QUOTE_MAX_CHARS = 500;

export function quoteOf(text: string): string {
  return Array.from(text).slice(0, QUOTE_MAX_CHARS).join("");
}
