/**
 * One listening session: the recognizer plus the timers that end it. Silence or a press ends it
 * through `stop`; a browser that never reports the end is cut off by a deadline (spec 115).
 */
import { type DictationLang, type Recognizer, createRecognizer } from "./speech";

/** Two seconds without a word ends the session (spec 115). */
export const SILENCE_MS = 2000;
/** After a stop, the browser has this long to report its last result before the session is closed. */
export const STOP_DEADLINE_MS = 1500;

export interface SessionCallbacks {
  onInterim: (text: string) => void;
  onFinal: (text: string) => void;
  onError: (code: string) => void;
  /** Called once, when the session is over; `heard` is true when a final phrase arrived. */
  onEnd: (heard: boolean) => void;
}

export interface Session {
  /** Let the browser finish the words it is hearing, then end. */
  stop: () => void;
  /** End now and drop what is pending; `onEnd` is not called. */
  abort: () => void;
}

/** Null when the browser cannot start a recognizer. */
export function startSession(
  lang: DictationLang,
  processLocally: boolean,
  callbacks: SessionCallbacks,
): Session | null {
  let live = true;
  let stopping = false;
  let heard = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let recognizer: Recognizer | null = null;

  const clear = () => {
    clearTimeout(timer);
    timer = undefined;
  };
  const finish = () => {
    if (!live) return;
    live = false;
    clear();
    callbacks.onEnd(heard);
  };
  const stop = () => {
    if (!live || stopping) return;
    stopping = true;
    clear();
    recognizer?.stop();
    if (live) timer = setTimeout(finish, STOP_DEADLINE_MS);
  };
  const arm = () => {
    if (stopping) return;
    clear();
    timer = setTimeout(stop, SILENCE_MS);
  };

  recognizer = createRecognizer({
    lang,
    processLocally,
    onInterim: (text) => {
      if (!live) return;
      callbacks.onInterim(text);
      arm();
    },
    onFinal: (text) => {
      if (!live) return;
      heard = true;
      callbacks.onFinal(text);
      arm();
    },
    onEnd: finish,
    onError: (code) => {
      if (live) callbacks.onError(code);
    },
  });
  if (!recognizer) return null;

  try {
    recognizer.start();
  } catch {
    live = false;
    clear();
    return null;
  }
  arm();
  return {
    stop,
    abort: () => {
      if (!live) return;
      live = false;
      clear();
      recognizer?.abort();
    },
  };
}
