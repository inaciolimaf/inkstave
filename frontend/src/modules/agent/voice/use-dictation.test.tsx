import { act, renderHook } from "@testing-library/react";
import type { KeyboardEvent } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CONSENT_KEY, LANG_KEY, SEND_AFTER_KEY } from "./preferences";
import type { DictationLang, RecognizerOptions } from "./speech";
import { appendSpoken, isDictationShortcut, langForInterface, useDictation } from "./use-dictation";

/** A recognizer the tests drive by hand: they call its options (the browser's events). */
const fake = vi.hoisted(() => {
  class FakeRecognizer {
    static all: FakeRecognizer[] = [];
    start = vi.fn();
    stop = vi.fn();
    abort = vi.fn();
    constructor(public options: RecognizerOptions) {
      FakeRecognizer.all.push(this);
    }
  }
  return { FakeRecognizer, supported: vi.fn(() => true), canLocal: vi.fn(async () => true) };
});

vi.mock("./speech", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./speech")>()),
  speechSupported: fake.supported,
  canProcessLocally: fake.canLocal,
  createRecognizer: (options: RecognizerOptions) => new fake.FakeRecognizer(options),
}));

type Options = Parameters<typeof useDictation>[0];

function setup(overrides: Partial<Options> = {}) {
  const callbacks = { onStart: vi.fn(), onFinal: vi.fn(), onEnd: vi.fn() };
  const hook = renderHook((props: Partial<Options>) => useDictation({ ...base(), ...callbacks, ...props }), {
    initialProps: overrides,
  });
  return { ...hook, ...callbacks };
}

function base(): Options {
  return {
    active: true,
    busy: false,
    interfaceLang: "en-US",
    onStart: vi.fn(),
    onFinal: vi.fn(),
    onEnd: vi.fn(),
  };
}

/** The recognizer of the session that is running now. */
function current() {
  const recognizer = fake.FakeRecognizer.all.at(-1);
  if (!recognizer) throw new Error("no recognizer was created");
  return recognizer;
}

async function press(result: { current: { toggle: () => void } }) {
  await act(async () => result.current.toggle());
}

beforeEach(() => {
  localStorage.clear();
  fake.FakeRecognizer.all = [];
  fake.supported.mockReturnValue(true);
  fake.canLocal.mockResolvedValue(true);
});

afterEach(() => vi.useRealTimers());

describe("useDictation: listening", () => {
  it("shows interim words, then passes each final phrase to the box", async () => {
    const { result, onFinal, onStart } = setup();
    await press(result);
    expect(result.current.state).toBe("listening");
    expect(onStart).toHaveBeenCalled();

    act(() => current().options.onInterim("troque o"));
    expect(result.current.interim).toBe("troque o");

    act(() => current().options.onFinal("troque o título"));
    expect(onFinal).toHaveBeenCalledWith("troque o título");
    expect(result.current.interim).toBe("");
  });

  it("stops when the user presses again, and returns to idle when the browser ends", async () => {
    const { result, onEnd } = setup();
    await press(result);
    await press(result);
    expect(current().stop).toHaveBeenCalled();

    act(() => {
      current().options.onFinal("Métodos");
      current().options.onEnd();
    });
    expect(result.current.state).toBe("idle");
    expect(onEnd).toHaveBeenCalledWith({ heard: true, sendAfter: false });
  });

  it("stops after two seconds of silence", async () => {
    vi.useFakeTimers();
    const { result } = setup();
    await press(result);
    act(() => vi.advanceTimersByTime(1999));
    expect(current().stop).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(1));
    expect(current().stop).toHaveBeenCalled();
  });

  it("restarts the silence count with each phrase", async () => {
    vi.useFakeTimers();
    const { result } = setup();
    await press(result);
    act(() => vi.advanceTimersByTime(1500));
    act(() => current().options.onInterim("ainda falando"));
    act(() => vi.advanceTimersByTime(1500));
    expect(current().stop).not.toHaveBeenCalled();
  });

  it("closes a session whose browser never reports the end", async () => {
    vi.useFakeTimers();
    const { result, onEnd } = setup();
    await press(result);
    await press(result);
    act(() => vi.advanceTimersByTime(1500));
    expect(result.current.state).toBe("idle");
    expect(onEnd).toHaveBeenCalledWith({ heard: false, sendAfter: false });
  });

  it("does not start while a run is in progress", async () => {
    const { result } = setup({ busy: true });
    await press(result);
    expect(result.current.state).toBe("idle");
    expect(fake.FakeRecognizer.all).toHaveLength(0);
  });

  it("does nothing when the browser has no speech recognition", async () => {
    fake.supported.mockReturnValue(false);
    const { result } = setup();
    expect(result.current.supported).toBe(false);
    await press(result);
    expect(fake.FakeRecognizer.all).toHaveLength(0);
  });
});

describe("useDictation: on-device and consent", () => {
  it("uses on-device recognition without asking when the browser has it", async () => {
    const { result } = setup();
    await press(result);
    expect(current().options.processLocally).toBe(true);
    expect(localStorage.getItem(CONSENT_KEY)).toBeNull();
  });

  it("asks before cloud recognition and starts nothing when cancelled", async () => {
    fake.canLocal.mockResolvedValue(false);
    const { result } = setup();
    await press(result);
    expect(result.current.state).toBe("asking-consent");
    expect(fake.FakeRecognizer.all).toHaveLength(0);

    act(() => result.current.answerConsent(false));
    expect(result.current.state).toBe("idle");
    expect(fake.FakeRecognizer.all).toHaveLength(0);
    expect(localStorage.getItem(CONSENT_KEY)).toBeNull();
  });

  it("starts cloud recognition after Continue, and remembers the choice", async () => {
    fake.canLocal.mockResolvedValue(false);
    const { result } = setup();
    await press(result);
    act(() => result.current.answerConsent(true));
    expect(result.current.state).toBe("listening");
    expect(current().options.processLocally).toBe(false);
    expect(localStorage.getItem(CONSENT_KEY)).toBe("1");

    act(() => current().options.onEnd());
    await press(result);
    expect(result.current.state).toBe("listening");
    expect(fake.FakeRecognizer.all).toHaveLength(2);
  });
});

describe("useDictation: errors", () => {
  it.each(["not-allowed", "no-speech", "network", "audio-capture"])("keeps the %s error", async (code) => {
    const { result } = setup();
    await press(result);
    act(() => {
      current().options.onError(code);
      current().options.onEnd();
    });
    expect(result.current.error).toBe(code);
    expect(result.current.state).toBe("idle");
  });

  it("maps an unexpected code to unknown", async () => {
    const { result } = setup();
    await press(result);
    act(() => current().options.onError("aborted-by-surprise"));
    expect(result.current.error).toBe("unknown");
  });

  it("clears the error on the next start", async () => {
    const { result } = setup();
    await press(result);
    act(() => current().options.onError("network"));
    act(() => current().options.onEnd());
    await press(result);
    expect(result.current.error).toBeNull();
  });
});

describe("useDictation: leaving", () => {
  it("cancels listening on unmount, and a late browser event sends nothing", async () => {
    const { result, unmount, onEnd, onFinal } = setup();
    await press(result);
    const recognizer = current();
    unmount();
    expect(recognizer.abort).toHaveBeenCalled();
    act(() => recognizer.options.onFinal("tarde demais"));
    act(() => recognizer.options.onEnd());
    expect(onFinal).not.toHaveBeenCalled();
    expect(onEnd).not.toHaveBeenCalled();
  });

  it("stops listening when the panel folds", async () => {
    const { result, rerender } = setup();
    await press(result);
    rerender({ active: false });
    expect(current().abort).toHaveBeenCalled();
    expect(result.current.state).toBe("idle");
  });

  it("cancel drops the session without reporting an end", async () => {
    const { result, onEnd } = setup();
    await press(result);
    act(() => result.current.cancel());
    expect(current().abort).toHaveBeenCalled();
    expect(result.current.state).toBe("idle");
    expect(onEnd).not.toHaveBeenCalled();
  });
});

describe("useDictation: sending and preferences", () => {
  it("reports sendAfter false by default, so dictation alone never sends", async () => {
    const { result, onEnd } = setup();
    await press(result);
    act(() => current().options.onFinal("Métodos"));
    act(() => current().options.onEnd());
    expect(onEnd).toHaveBeenCalledWith({ heard: true, sendAfter: false });
  });

  it("reports sendAfter true once the user turns the preference on", async () => {
    const { result, onEnd } = setup();
    act(() => result.current.setSendAfter(true));
    expect(localStorage.getItem(SEND_AFTER_KEY)).toBe("1");
    await press(result);
    act(() => current().options.onFinal("Métodos"));
    act(() => current().options.onEnd());
    expect(onEnd).toHaveBeenCalledWith({ heard: true, sendAfter: true });
  });

  it("picks the recognition language from the interface, then remembers the user's choice", () => {
    const { result } = setup({ interfaceLang: "pt-BR" });
    expect(result.current.lang).toBe("pt-BR");
    act(() => result.current.setLang("en-US"));
    expect(localStorage.getItem(LANG_KEY)).toBe("en-US");
  });

  it("starts the recognizer in the language the user picked", async () => {
    localStorage.setItem(LANG_KEY, "en-US" satisfies DictationLang);
    const { result } = setup({ interfaceLang: "pt-BR" });
    await press(result);
    expect(current().options.lang).toBe("en-US");
  });
});

describe("dictation helpers", () => {
  it("joins spoken words to the draft with one space", () => {
    expect(appendSpoken("", "Métodos")).toBe("Métodos");
    expect(appendSpoken("Seção 2", "Métodos")).toBe("Seção 2 Métodos");
    expect(appendSpoken("Seção 2 ", "Métodos")).toBe("Seção 2 Métodos");
  });

  it("maps the interface language to a recognition language", () => {
    expect(langForInterface("pt")).toBe("pt-BR");
    expect(langForInterface("pt-BR")).toBe("pt-BR");
    expect(langForInterface("en-GB")).toBe("en-US");
  });

  it("recognises Ctrl+Shift+M and Cmd+Shift+M only", () => {
    const key = (init: KeyboardEventInit) => ({ key: "M", ...init }) as unknown as KeyboardEvent;
    expect(isDictationShortcut(key({ ctrlKey: true, shiftKey: true }))).toBe(true);
    expect(isDictationShortcut(key({ metaKey: true, shiftKey: true }))).toBe(true);
    expect(isDictationShortcut(key({ ctrlKey: true }))).toBe(false);
  });
});
