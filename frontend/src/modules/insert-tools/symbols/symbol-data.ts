import symbolData from "./symbols.json";

export const SYMBOL_CATEGORIES = [
  "greek",
  "relations",
  "operators",
  "arrows",
  "sets",
  "delimiters",
  "accents",
  "misc",
] as const;

export type SymbolCategory = (typeof SYMBOL_CATEGORIES)[number];

/** One entry of `symbols.json`. `args` counts the `{}` the command takes; `package` is what it needs. */
export interface SymbolEntry {
  command: string;
  unicode: string;
  category: SymbolCategory;
  keywords: string[];
  package?: string;
  args?: number;
}

export const SYMBOLS = symbolData as SymbolEntry[];

const rank = (entry: SymbolEntry, needle: string) => (bare(entry).startsWith(needle) ? 0 : 1);
const bare = (entry: SymbolEntry) => entry.command.slice(1).toLowerCase();

function matches(entry: SymbolEntry, needle: string): boolean {
  return bare(entry).includes(needle) || entry.keywords.some((word) => word.toLowerCase().includes(needle));
}

/** Symbols whose command or keyword contains the query, a command that starts with it first. */
export function searchSymbols(query: string, category: SymbolCategory | "all"): SymbolEntry[] {
  const needle = query.trim().toLowerCase().replace(/^\\/, "");
  return SYMBOLS.filter((entry) => category === "all" || entry.category === category)
    .filter((entry) => needle === "" || matches(entry, needle))
    .sort((a, b) => rank(a, needle) - rank(b, needle));
}

export function findSymbol(command: string): SymbolEntry | undefined {
  return SYMBOLS.find((entry) => entry.command === command);
}
