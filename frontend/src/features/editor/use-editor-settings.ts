import { useCallback, useEffect, useState } from "react";

import type { EditorSettings } from "./types";

const STORAGE_KEY = "inkstave:editor-settings";
export const MIN_FONT = 10;
export const MAX_FONT = 24;
const DEFAULTS: EditorSettings = { fontSize: 14, keymap: "default", lineWrapping: true };

export function clampFontSize(n: number): number {
  return Math.min(MAX_FONT, Math.max(MIN_FONT, Math.round(n)));
}

function load(): EditorSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULTS;
    const parsed = JSON.parse(raw) as Partial<EditorSettings>;
    return {
      ...DEFAULTS,
      ...parsed,
      fontSize: clampFontSize(parsed.fontSize ?? DEFAULTS.fontSize),
    };
  } catch {
    return DEFAULTS;
  }
}

export function useEditorSettings() {
  const [settings, setSettings] = useState<EditorSettings>(load);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
    } catch {
      /* ignore */
    }
  }, [settings]);

  const update = useCallback((patch: Partial<EditorSettings>) => {
    setSettings((prev) => {
      const next = { ...prev, ...patch };
      if (patch.fontSize != null) next.fontSize = clampFontSize(patch.fontSize);
      return next;
    });
  }, []);

  return { settings, update };
}
