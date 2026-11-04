import { afterEach, describe, expect, it, vi } from "vitest";

import { canProcessLocally, createRecognizer, speechSupported } from "./speech";

/** A stand-in for the browser's SpeechRecognition; the tests drive its events by hand. */
class FakeBrowserRecognition {
  static instances: FakeBrowserRecognition[] = [];
  static available = vi.fn<(options: unknown) => Promise<string>>();
  lang = "";
  continuous = false;
  interimResults = false;
  processLocally?: boolean;
  onresult: ((event: unknown) => void) | null = null;
  onend: (() => void) | null = null;
  onerror: ((event: { error: string }) => void) | null = null;
  start = vi.fn();
  stop = vi.fn();
  abort = vi.fn();
  constructor() {
    FakeBrowserRecognition.instances.push(this);
  }
}

function result(transcript: string, isFinal: boolean) {
  return { isFinal, 0: { transcript } };
}

function options(overrides: Partial<Parameters<typeof createRecognizer>[0]> = {}) {
  return {
    lang: "pt-BR" as const,
    processLocally: false,
    onInterim: vi.fn(),
    onFinal: vi.fn(),
    onEnd: vi.fn(),
    onError: vi.fn(),
    ...overrides,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
  FakeBrowserRecognition.instances = [];
  FakeBrowserRecognition.available.mockReset();
});

describe("speech feature detection", () => {
  it("reports no support and creates nothing where the browser has no recognition", () => {
    expect(speechSupported()).toBe(false);
    expect(createRecognizer(options())).toBeNull();
  });

  it("finds the prefixed constructor too (webkitSpeechRecognition)", () => {
    vi.stubGlobal("webkitSpeechRecognition", FakeBrowserRecognition);
    expect(speechSupported()).toBe(true);
  });
});

describe("createRecognizer", () => {
  it("configures a continuous, interim recognizer in the chosen language", () => {
    vi.stubGlobal("SpeechRecognition", FakeBrowserRecognition);
    createRecognizer(options({ lang: "en-US" }));
    const [recognition] = FakeBrowserRecognition.instances;
    expect(recognition.lang).toBe("en-US");
    expect(recognition.continuous).toBe(true);
    expect(recognition.interimResults).toBe(true);
    expect(recognition.processLocally).toBeUndefined();
  });

  it("asks for on-device processing only when told to", () => {
    vi.stubGlobal("SpeechRecognition", FakeBrowserRecognition);
    createRecognizer(options({ processLocally: true }));
    expect(FakeBrowserRecognition.instances[0].processLocally).toBe(true);
  });

  it("passes final phrases once and the pending words as interim text", () => {
    vi.stubGlobal("SpeechRecognition", FakeBrowserRecognition);
    const opts = options();
    createRecognizer(opts);
    const [recognition] = FakeBrowserRecognition.instances;
    recognition.onresult?.({
      resultIndex: 0,
      results: [result("troque o título", true), result("da seção", false)],
    });
    expect(opts.onFinal).toHaveBeenCalledWith("troque o título");
    expect(opts.onInterim).toHaveBeenCalledWith("da seção");
  });

  it("reads only the results that changed since the last event", () => {
    vi.stubGlobal("SpeechRecognition", FakeBrowserRecognition);
    const opts = options();
    createRecognizer(opts);
    const [recognition] = FakeBrowserRecognition.instances;
    recognition.onresult?.({
      resultIndex: 1,
      results: [result("primeira", true), result("segunda", true)],
    });
    expect(opts.onFinal).toHaveBeenCalledTimes(1);
    expect(opts.onFinal).toHaveBeenCalledWith("segunda");
  });

  it("relays end and error events, and delegates start, stop and abort", () => {
    vi.stubGlobal("SpeechRecognition", FakeBrowserRecognition);
    const opts = options();
    const recognizer = createRecognizer(opts);
    const [recognition] = FakeBrowserRecognition.instances;
    recognizer?.start();
    recognizer?.stop();
    recognizer?.abort();
    recognition.onerror?.({ error: "not-allowed" });
    recognition.onend?.();
    expect(recognition.start).toHaveBeenCalled();
    expect(recognition.stop).toHaveBeenCalled();
    expect(recognition.abort).toHaveBeenCalled();
    expect(opts.onError).toHaveBeenCalledWith("not-allowed");
    expect(opts.onEnd).toHaveBeenCalled();
  });
});

describe("canProcessLocally", () => {
  it("is true only when the browser answers available for the language", async () => {
    vi.stubGlobal("SpeechRecognition", FakeBrowserRecognition);
    FakeBrowserRecognition.available.mockResolvedValue("available");
    await expect(canProcessLocally("pt-BR")).resolves.toBe(true);
    expect(FakeBrowserRecognition.available).toHaveBeenCalledWith({
      langs: ["pt-BR"],
      processLocally: true,
    });
  });

  it("is false when the language must still be downloaded", async () => {
    vi.stubGlobal("SpeechRecognition", FakeBrowserRecognition);
    FakeBrowserRecognition.available.mockResolvedValue("downloadable");
    await expect(canProcessLocally("en-US")).resolves.toBe(false);
  });

  it("is false when the check fails or the browser has no availability API", async () => {
    vi.stubGlobal("SpeechRecognition", FakeBrowserRecognition);
    FakeBrowserRecognition.available.mockRejectedValue(new Error("nope"));
    await expect(canProcessLocally("en-US")).resolves.toBe(false);

    vi.stubGlobal("SpeechRecognition", class {});
    await expect(canProcessLocally("en-US")).resolves.toBe(false);
  });
});
