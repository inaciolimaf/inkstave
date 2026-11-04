/**
 * The spell checker itself: nspell over a Hunspell dictionary, loaded from the static files next to the
 * app. It runs inside the worker (spell.worker.ts) and is kept free of worker globals so the tests can run
 * it with a fake `fetch`. It sends no document text anywhere: the only requests it makes are for the
 * dictionary files.
 */
import nspell from "nspell";

import { MAX_SUGGESTIONS, type DictionaryLanguage, isDictionaryLanguage } from "./types";

/** The part of nspell this engine uses. */
export interface SpellDictionary {
  correct(word: string): boolean;
  suggest(word: string): string[];
}

export type FetchText = (url: string) => Promise<string>;

export interface SpellEngine {
  check(language: DictionaryLanguage, words: string[]): Promise<string[]>;
  suggest(language: DictionaryLanguage, word: string): Promise<string[]>;
}

/** `base` is the app's base URL, from which `dictionaries/<language>.aff|.dic` are served. */
export function createSpellEngine(fetchText: FetchText, base: string): SpellEngine {
  const loaded = new Map<DictionaryLanguage, Promise<SpellDictionary>>();

  function dictionary(language: string): Promise<SpellDictionary> {
    if (!isDictionaryLanguage(language)) return Promise.reject(new Error(`Unknown language ${language}`));
    const cached = loaded.get(language);
    if (cached) return cached;
    const pending = loadDictionary(fetchText, base, language);
    loaded.set(language, pending);
    // A failed load is forgotten so the next request can try again.
    pending.catch(() => loaded.delete(language));
    return pending;
  }

  return {
    async check(language, words) {
      const spell = await dictionary(language);
      return words.filter((word) => !spell.correct(word));
    },
    async suggest(language, word) {
      const spell = await dictionary(language);
      return spell.suggest(word).slice(0, MAX_SUGGESTIONS);
    },
  };
}

async function loadDictionary(
  fetchText: FetchText,
  base: string,
  language: DictionaryLanguage,
): Promise<SpellDictionary> {
  const stem = `${base}dictionaries/${language}`;
  const [aff, dic] = await Promise.all([fetchText(`${stem}.aff.gz`), fetchText(`${stem}.dic.gz`)]);
  return nspell(aff, dic);
}

const GZIP_MAGIC = [0x1f, 0x8b];

/**
 * Reads a dictionary file. The build gzips them (`scripts/copy-dictionaries.mjs`), so the bytes are
 * unzipped here. A server that already unzips the response (a `Content-Encoding` header) hands over plain
 * text, which the magic-number check lets through.
 */
export async function decodeDictionary(bytes: Uint8Array): Promise<string> {
  if (bytes[0] !== GZIP_MAGIC[0] || bytes[1] !== GZIP_MAGIC[1]) return new TextDecoder().decode(bytes);
  const unzipped = new Response(new Uint8Array(bytes)).body!.pipeThrough(new DecompressionStream("gzip"));
  return new Response(unzipped).text();
}

/** The browser's fetch, for a dictionary file that must exist. */
export async function fetchDictionaryText(url: string): Promise<string> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Dictionary request failed: ${response.status}`);
  return decodeDictionary(new Uint8Array(await response.arrayBuffer()));
}
