import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join, resolve } from "node:path";

import { describe, expect, it, vi } from "vitest";

import { createSpellEngine, decodeDictionary, type FetchBytes } from "./spell-engine";

// A tiny Hunspell pair, so the tests never load a real dictionary.
const AFF = "SET UTF-8\nTRY esianrtolcdugmphbyfvkwz\n";
const DIC = "4\nthe\ncat\nmethodology\nsat\n";

function fakeFetch(files: Record<string, string>) {
  const requested: string[] = [];
  const fetchText = vi.fn<FetchBytes>(async (url) => {
    requested.push(url);
    const body = files[url];
    if (body === undefined) throw new Error(`404 ${url}`);
    return new TextEncoder().encode(body);
  });
  return { fetchText, requested };
}

const FILES = {
  "/dictionaries/en-US.aff.gz": AFF,
  "/dictionaries/en-US.dic.gz": DIC,
};

describe("spell engine", () => {
  it("reports the words the dictionary does not know", async () => {
    const { fetchText } = fakeFetch(FILES);
    const engine = createSpellEngine(fetchText, "/");
    expect(await engine.check("en-US", ["the", "teh", "methodology", "methodolgia"])).toEqual([
      "teh",
      "methodolgia",
    ]);
  });

  it("suggests corrections, at most five", async () => {
    const { fetchText } = fakeFetch(FILES);
    const engine = createSpellEngine(fetchText, "/");
    const suggestions = await engine.suggest("en-US", "teh");
    expect(suggestions).toContain("the");
    expect(suggestions.length).toBeLessThanOrEqual(5);
  });

  it("loads each dictionary once, from the dictionaries folder only", async () => {
    const { fetchText, requested } = fakeFetch(FILES);
    const engine = createSpellEngine(fetchText, "/");
    await engine.check("en-US", ["teh"]);
    await engine.suggest("en-US", "teh");
    await engine.check("en-US", ["cat"]);
    expect(requested.sort()).toEqual(["/dictionaries/en-US.aff.gz", "/dictionaries/en-US.dic.gz"]);
  });

  it("forgets a failed load so the next request tries again", async () => {
    const { fetchText } = fakeFetch({});
    const engine = createSpellEngine(fetchText, "/");
    await expect(engine.check("en-US", ["teh"])).rejects.toThrow();
    await expect(engine.check("en-US", ["teh"])).rejects.toThrow();
    expect(fetchText).toHaveBeenCalledTimes(4);
  });

  it("refuses a language that has no dictionary", async () => {
    const { fetchText } = fakeFetch(FILES);
    const engine = createSpellEngine(fetchText, "/");
    await expect(engine.check("fr-FR" as "en-US", ["teh"])).rejects.toThrow(/Unknown language/);
    expect(fetchText).not.toHaveBeenCalled();
  });
});

describe("the real pt-BR dictionary", () => {
  // Regression: nspell never finished building this dictionary, so Portuguese spell check never loaded.
  it("loads in a few seconds and knows Portuguese words", async () => {
    const dir = dirname(createRequire(import.meta.url).resolve("dictionary-pt"));
    const files: Record<string, Uint8Array> = {
      "/dictionaries/pt-BR.aff.gz": readFileSync(join(dir, "index.aff")),
      "/dictionaries/pt-BR.dic.gz": readFileSync(join(dir, "index.dic")),
    };
    const engine = createSpellEngine(async (url) => files[url]!, "/");
    const words = ["contribuições", "seguem", "Revisão", "trabalhao"];
    expect(await engine.check("pt-BR", words)).toEqual(["trabalhao"]);
    expect(await engine.suggest("pt-BR", "trabalhao")).toContain("trabalho");
  }, 10_000);
});

describe("dictionary files", () => {
  async function gzip(text: string): Promise<Uint8Array> {
    const body = new Response(new TextEncoder().encode(text)).body!;
    const compressed = new Response(body.pipeThrough(new CompressionStream("gzip")));
    return new Uint8Array(await compressed.arrayBuffer());
  }

  it("unzips a gzipped dictionary", async () => {
    expect(new TextDecoder().decode(await decodeDictionary(await gzip(DIC)))).toBe(DIC);
  });

  it("takes plain bytes as they are when the server has already unzipped them", async () => {
    const plain = new TextEncoder().encode(AFF);
    expect(await decodeDictionary(plain)).toBe(plain);
  });
});

describe("spell worker guarantee", () => {
  const sources = ["spell.worker.ts", "spell-engine.ts", "spell-protocol.ts", "spell-client.ts"].map((name) =>
    readFileSync(resolve("src/modules/spellcheck", name), "utf-8"),
  );
  const worker = sources[0];
  const engine = sources[1];

  it("has no network API besides fetching the dictionary files", () => {
    for (const source of sources.slice(0, 2)) {
      expect(source).not.toMatch(/XMLHttpRequest|WebSocket|sendBeacon|EventSource|importScripts|navigator/);
    }
    expect(worker).not.toMatch(/\bfetch\(/);
    // The one fetch in the engine reads a dictionary file, never a value from the document.
    expect(engine.match(/fetch\(/g)).toHaveLength(1);
    expect(engine).toMatch(/fetch\(url\)/);
    expect(engine).toMatch(/dictionaries\/\$\{language\}/);
  });
});
