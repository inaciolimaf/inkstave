import { useCallback, useEffect, useState } from "react";

import type { EditorSettings } from "./types";

const STORAGE_KEY = "inkstave:editor-settings";
const DEFAULTS: EditorSettings = { fontSize: 14, keymap: "default", lineWrapping: true };

function load(): EditorSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULTS;
    const parsed = JSON.parse(raw) as Partial<EditorSettings>;
    return { ...DEFAULTS, ...parsed };
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
    setSettings((prev) => ({ ...prev, ...patch }));
  }, []);

  return { settings, update };
}
