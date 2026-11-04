import { findSymbol, type SymbolEntry } from "./symbol-data";

/** The commands used lately, kept per browser (spec 114 §5.2). Storage may be blocked: then there are none. */
const KEY = "inkstave.insert.recent-symbols";
export const RECENT_LIMIT = 16;

export function readRecent(): string[] {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(KEY) ?? "[]");
    return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === "string") : [];
  } catch {
    return [];
  }
}

/** Puts a command first in the list, keeps the limit, and returns the new list. */
export function rememberRecent(command: string): string[] {
  const next = [command, ...readRecent().filter((item) => item !== command)].slice(0, RECENT_LIMIT);
  try {
    localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    // Blocked storage only loses the convenience.
  }
  return next;
}

/** The recent commands that still exist in the palette, in order. */
export function recentEntries(commands: string[]): SymbolEntry[] {
  return commands.map(findSymbol).filter((entry): entry is SymbolEntry => entry !== undefined);
}
