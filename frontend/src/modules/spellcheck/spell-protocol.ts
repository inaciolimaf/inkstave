/** Messages between the editor and the spell worker (spec 113). */
import type { DictionaryLanguage } from "./types";

export type SpellOperation =
  | { op: "check"; language: DictionaryLanguage; words: string[] }
  | { op: "suggest"; language: DictionaryLanguage; word: string };

/** `base` is the app's base URL, where the dictionary files are served from. */
export type SpellRequest = SpellOperation & { id: number; base: string };

export type SpellResponse =
  | { id: number; ok: true; result: string[] }
  | { id: number; ok: false; error: string };
