/**
 * The only file that touches the browser's speech recognition (spec 115). It hands text to the
 * caller and never sees, stores or sends audio: the browser captures the microphone itself.
 */

export type DictationLang = "en-US" | "pt-BR";

export interface RecognizerOptions {
  lang: DictationLang;
  processLocally: boolean;
  onInterim: (text: string) => void;
  onFinal: (text: string) => void;
  onEnd: () => void;
  onError: (code: string) => void;
}

export interface Recognizer {
  start: () => void;
  stop: () => void;
  abort: () => void;
}

interface RecognitionResultLike {
  readonly isFinal: boolean;
  readonly 0: { readonly transcript: string };
}

interface RecognitionEventLike {
  readonly resultIndex: number;
  readonly results: ArrayLike<RecognitionResultLike>;
}

interface RecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  processLocally?: boolean;
  onresult: ((event: RecognitionEventLike) => void) | null;
  onend: (() => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
}

interface RecognitionConstructor {
  new (): RecognitionLike;
  available?: (options: { langs: string[]; processLocally: boolean }) => Promise<string>;
}

type SpeechWindow = Window & {
  SpeechRecognition?: RecognitionConstructor;
  webkitSpeechRecognition?: RecognitionConstructor;
};

function recognitionConstructor(): RecognitionConstructor | undefined {
  if (typeof window === "undefined") return undefined;
  const w = window as SpeechWindow;
  return w.SpeechRecognition ?? w.webkitSpeechRecognition;
}

export function speechSupported(): boolean {
  return recognitionConstructor() !== undefined;
}

/** True when the browser says it can recognise `lang` on the device, so no audio leaves it. */
export async function canProcessLocally(lang: DictationLang): Promise<boolean> {
  const ctor = recognitionConstructor();
  if (!ctor?.available) return false;
  try {
    return (await ctor.available({ langs: [lang], processLocally: true })) === "available";
  } catch {
    return false;
  }
}

/** Final results are passed on once each; the words still being decided are the interim text. */
function readResults(event: RecognitionEventLike, options: RecognizerOptions) {
  let interim = "";
  for (let i = event.resultIndex; i < event.results.length; i++) {
    const result = event.results[i];
    const text = result[0].transcript.trim();
    if (result.isFinal) {
      if (text) options.onFinal(text);
    } else {
      interim += ` ${text}`;
    }
  }
  options.onInterim(interim.trim());
}

/** Null when the browser has no speech recognition, so the caller can hide the feature. */
export function createRecognizer(options: RecognizerOptions): Recognizer | null {
  const ctor = recognitionConstructor();
  if (!ctor) return null;
  const recognition = new ctor();
  recognition.lang = options.lang;
  recognition.continuous = true;
  recognition.interimResults = true;
  if (options.processLocally) recognition.processLocally = true;
  recognition.onresult = (event) => readResults(event, options);
  recognition.onend = () => options.onEnd();
  recognition.onerror = (event) => options.onError(event.error);
  return {
    start: () => recognition.start(),
    stop: () => recognition.stop(),
    abort: () => recognition.abort(),
  };
}
