/**
 * The spell-check worker: one per tab, reused across documents (spec 113). It answers `check` and
 * `suggest` requests with the engine of `spell-engine.ts`. Its only network calls fetch dictionary files;
 * the text of the document never leaves the browser.
 */
import { createSpellEngine, fetchDictionaryBytes, type SpellEngine } from "./spell-engine";
import type { SpellRequest, SpellResponse } from "./spell-protocol";

/** Created by the first request, which carries the base URL the dictionaries are served from. */
let engine: SpellEngine | null = null;

function engineFor(base: string): SpellEngine {
  engine ??= createSpellEngine(fetchDictionaryBytes, base);
  return engine;
}

function answer(request: SpellRequest): Promise<string[]> {
  const spell = engineFor(request.base);
  if (request.op === "check") return spell.check(request.language, request.words);
  return spell.suggest(request.language, request.word);
}

self.onmessage = (event: MessageEvent<SpellRequest>) => {
  const request = event.data;
  answer(request).then(
    (result) => self.postMessage({ id: request.id, ok: true, result } satisfies SpellResponse),
    (error: unknown) =>
      self.postMessage({
        id: request.id,
        ok: false,
        error: error instanceof Error ? error.message : String(error),
      } satisfies SpellResponse),
  );
};
