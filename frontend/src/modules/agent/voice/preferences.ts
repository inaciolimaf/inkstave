/** Dictation choices kept per browser in localStorage. Storage can be blocked, so every access is guarded. */
import { useState } from "react";

import type { DictationLang } from "./speech";

export const CONSENT_KEY = "inkstave.agent.dictation.cloudConsent";
export const SEND_AFTER_KEY = "inkstave.agent.dictation.sendAfter";
export const LANG_KEY = "inkstave.agent.dictation.lang";

export function readFlag(key: string): boolean {
  try {
    return localStorage.getItem(key) === "1";
  } catch {
    return false;
  }
}

export function writeFlag(key: string, value: boolean): void {
  try {
    localStorage.setItem(key, value ? "1" : "0");
  } catch {
    // Storage is blocked: the choice lasts for this page only.
  }
}

export function readLang(): DictationLang | null {
  try {
    const value = localStorage.getItem(LANG_KEY);
    return value === "en-US" || value === "pt-BR" ? value : null;
  } catch {
    return null;
  }
}

export function writeLang(lang: DictationLang): void {
  try {
    localStorage.setItem(LANG_KEY, lang);
  } catch {
    // Storage is blocked: the choice lasts for this page only.
  }
}

/** A flag that is read once and kept in state, so the screen follows what the user picked. */
export function useStoredFlag(key: string): [boolean, (value: boolean) => void] {
  const [value, setValue] = useState(() => readFlag(key));
  return [
    value,
    (next) => {
      writeFlag(key, next);
      setValue(next);
    },
  ];
}

export function useStoredLang(fallback: DictationLang): [DictationLang, (lang: DictationLang) => void] {
  const [value, setValue] = useState(() => readLang() ?? fallback);
  return [
    value,
    (next) => {
      writeLang(next);
      setValue(next);
    },
  ];
}
