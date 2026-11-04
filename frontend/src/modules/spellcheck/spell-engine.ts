/**
 * The spell checker itself: Hunspell compiled to WebAssembly (`hunspell-asm`) over the dictionary files
 * served next to the app (ADR 0122: nspell, the first engine, never finished building the pt-BR dictionary).
 * It runs inside the worker (spell.worker.ts) and is kept free of worker globals so the tests can run it with
 * a fake `fetch`. It sends no document text anywhere: the only requests it makes are for the
 * dictionary files.
 */
import { loadModule, type HunspellFactory } from "hunspell-asm";

import { MAX_SUGGESTIONS, type DictionaryLanguage, isDictionaryLanguage } from "./types";

/** The part of Hunspell this engine uses. */
export interface SpellDictionary {
  correct(word: string): boolean;
  suggest(word: string): string[];
}

export type FetchBytes = (url: string) => Promise<Uint8Array>;

export interface SpellEngine {
  check(language: DictionaryLanguage, words: string[]): Promise<string[]>;
  suggest(language: DictionaryLanguage, word: string): Promise<string[]>;
}

/** `base` is the app's base URL, from which `dictionaries/<language>.aff|.dic` are served. */
export function createSpellEngine(fetchBytes: FetchBytes, base: string): SpellEngine {
  const loaded = new Map<DictionaryLanguage, Promise<SpellDictionary>>();

  function dictionary(language: string): Promise<SpellDictionary> {
    if (!isDictionaryLanguage(language)) return Promise.reject(new Error(`Unknown language ${language}`));
    const cached = loaded.get(language);
    if (cached) return cached;
    const pending = loadDictionary(fetchBytes, base, language);
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

/** The WebAssembly module, compiled once per worker and shared by every language. */
let factory: Promise<HunspellFactory> | null = null;

async function loadDictionary(
  fetchBytes: FetchBytes,
  base: string,
  language: DictionaryLanguage,
): Promise<SpellDictionary> {
  const stem = `${base}dictionaries/${language}`;
  factory ??= loadModule();
  const [hunspell, aff, dic] = await Promise.all([
    factory,
    fetchBytes(`${stem}.aff.gz`),
    fetchBytes(`${stem}.dic.gz`),
  ]);
  const affPath = hunspell.mountBuffer(aff, `${language}.aff`);
  const dicPath = hunspell.mountBuffer(dic, `${language}.dic`);
  const instance = hunspell.create(affPath, dicPath);
  // Hunspell has read both files; the copies in the virtual file system are no longer needed.
  hunspell.unmount(affPath);
  hunspell.unmount(dicPath);
  return { correct: (word) => instance.spell(word), suggest: (word) => instance.suggest(word) };
}

const GZIP_MAGIC = [0x1f, 0x8b];

/**
 * Reads a dictionary file. The build gzips them (`scripts/copy-dictionaries.mjs`), so the bytes are
 * unzipped here. A server that already unzips the response (a `Content-Encoding` header) hands over plain
 * bytes, which the magic-number check lets through.
 */
export async function decodeDictionary(bytes: Uint8Array): Promise<Uint8Array> {
  if (bytes[0] !== GZIP_MAGIC[0] || bytes[1] !== GZIP_MAGIC[1]) return bytes;
  const unzipped = new Response(new Uint8Array(bytes)).body!.pipeThrough(new DecompressionStream("gzip"));
  return new Uint8Array(await new Response(unzipped).arrayBuffer());
}

/** The browser's fetch, for a dictionary file that must exist. */
export async function fetchDictionaryBytes(url: string): Promise<Uint8Array> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Dictionary request failed: ${response.status}`);
  return decodeDictionary(new Uint8Array(await response.arrayBuffer()));
}
