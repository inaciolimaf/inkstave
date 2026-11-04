import { useCallback, useEffect, useState } from "react";

import type { EditorSettings } from "./types";

/** Only the line wrapping is kept here (spec 59 moved the rest to the account, spec 112 added autocomplete). */
type LocalSettings = Omit<EditorSettings, "autocomplete">;

const STORAGE_KEY = "inkstave:editor-settings";
const DEFAULTS: LocalSettings = { fontSize: 14, keymap: "default", lineWrapping: true };

function load(): LocalSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULTS;
    const parsed = JSON.parse(raw) as Partial<LocalSettings>;
    return { ...DEFAULTS, ...parsed };
  } catch {
    return DEFAULTS;
  }
}

export function useEditorSettings() {
  const [settings, setSettings] = useState<LocalSettings>(load);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
    } catch {
      /* ignore */
    }
  }, [settings]);

  const update = useCallback((patch: Partial<LocalSettings>) => {
    setSettings((prev) => ({ ...prev, ...patch }));
  }, []);

  return { settings, update };
}
