/**
 * Dictation for the agent's message box (spec 115): idle → asking-consent → listening → idle.
 * The words land in the box through `onFinal`; nothing is sent unless the user chose "send after".
 */
import type { KeyboardEvent } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

import { canProcessLocally, type DictationLang, speechSupported } from "./speech";
import { type Session, startSession } from "./session";
import {
  CONSENT_KEY,
  readFlag,
  SEND_AFTER_KEY,
  useStoredFlag,
  useStoredLang,
  writeFlag,
} from "./preferences";

export type DictationState = "idle" | "asking-consent" | "listening";

export interface DictationEnd {
  heard: boolean;
  sendAfter: boolean;
}

export interface DictationOptions {
  /** False while the agent window is folded: a folded window stops listening. */
  active: boolean;
  /** True while a run is in progress: dictation cannot start. */
  busy: boolean;
  /** The interface language, which picks the recognition language until the user chooses one. */
  interfaceLang: string;
  onStart: () => void;
  onFinal: (text: string) => void;
  onEnd: (end: DictationEnd) => void;
}

export interface DictationApi {
  supported: boolean;
  state: DictationState;
  interim: string;
  error: string | null;
  lang: DictationLang;
  setLang: (lang: DictationLang) => void;
  sendAfter: boolean;
  setSendAfter: (value: boolean) => void;
  toggle: () => void;
  stop: () => void;
  cancel: () => void;
  answerConsent: (accept: boolean) => void;
}

export function langForInterface(language: string): DictationLang {
  return language.toLowerCase().startsWith("pt") ? "pt-BR" : "en-US";
}

/** Adds spoken words to the draft with one space between, never at its start. */
export function appendSpoken(draft: string, spoken: string): string {
  if (!draft || /\s$/.test(draft)) return draft + spoken;
  return `${draft} ${spoken}`;
}

/** Ctrl+Shift+M, or Cmd+Shift+M on a Mac. */
export function isDictationShortcut(e: KeyboardEvent): boolean {
  return Boolean((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === "m");
}

const KNOWN_ERRORS = ["not-allowed", "no-speech", "network", "audio-capture"];

/** An error the screen has a message for; anything else reads as "unknown". */
function knownError(error: string | null): string | null {
  if (error === null) return null;
  return KNOWN_ERRORS.includes(error) ? error : "unknown";
}

export function useDictation(options: DictationOptions): DictationApi {
  const [supported] = useState(speechSupported);
  const [state, setState] = useState<DictationState>("idle");
  const [interim, setInterim] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [lang, setLang] = useStoredLang(langForInterface(options.interfaceLang));
  const [sendAfter, setSendAfter] = useStoredFlag(SEND_AFTER_KEY);
  // Callbacks read through a ref so a recognizer event always sees the latest panel state.
  const latest = useRef({ ...options, sendAfter });
  latest.current = { ...options, sendAfter };
  const session = useRef<Session | null>(null);
  const starting = useRef(false);
  const mounted = useRef(false);

  const cancel = useCallback(() => {
    session.current?.abort();
    session.current = null;
    setState("idle");
    setInterim("");
  }, []);

  const listen = useCallback(
    (processLocally: boolean) => {
      setError(null);
      const started = startSession(lang, processLocally, {
        onInterim: setInterim,
        onFinal: (text) => {
          setInterim("");
          latest.current.onFinal(text);
        },
        onError: setError,
        onEnd: (heard) => {
          session.current = null;
          setState("idle");
          setInterim("");
          latest.current.onEnd({ heard, sendAfter: latest.current.sendAfter });
        },
      });
      if (!started) {
        setError("unknown");
        return;
      }
      session.current = started;
      setState("listening");
      latest.current.onStart();
    },
    [lang],
  );

  const begin = useCallback(async () => {
    starting.current = true;
    try {
      const processLocally = await canProcessLocally(lang);
      if (!mounted.current || !latest.current.active) return;
      if (!processLocally && !readFlag(CONSENT_KEY)) setState("asking-consent");
      else listen(processLocally);
    } finally {
      starting.current = false;
    }
  }, [lang, listen]);

  const toggle = useCallback(() => {
    if (session.current) {
      session.current.stop();
      return;
    }
    if (!supported || state !== "idle" || starting.current || latest.current.busy) return;
    void begin();
  }, [begin, state, supported]);

  const answerConsent = useCallback(
    (accept: boolean) => {
      if (!accept) {
        setState("idle");
        return;
      }
      writeFlag(CONSENT_KEY, true);
      listen(false);
    },
    [listen],
  );

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      cancel();
    };
  }, [cancel]);

  useEffect(() => {
    if (!options.active) cancel();
  }, [options.active, cancel]);

  return {
    supported,
    state,
    interim,
    error: knownError(error),
    lang,
    setLang,
    sendAfter,
    setSendAfter,
    toggle,
    stop: () => session.current?.stop(),
    cancel,
    answerConsent,
  };
}
