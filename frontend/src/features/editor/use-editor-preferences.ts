import { useCallback } from "react";

import { useAuth } from "@/auth/auth-context";
import { putEditorPreferences } from "@/features/settings/api";
import { DEFAULT_EDITOR_PREFERENCES, type EditorPreferences } from "@/types";

import { resolveDark } from "./resolve-theme";
import type { EditorSettings } from "./types";
import { useEditorSettings } from "./use-editor-settings";
import { useIsDark } from "./use-is-dark";

/**
 * The editor's settings, sourced from the user's server-side preferences (spec
 * 59): theme/font-size/keymap come from the account, while line-wrapping stays a
 * local-only toggle. Updates persist to the server and optimistically update the
 * cached user so the open editor reconfigures live.
 */
export function useEditorPreferences(): {
  settings: EditorSettings;
  dark: boolean;
  update: (patch: Partial<EditorSettings>) => void;
} {
  const { user, applyUser } = useAuth();
  const systemDark = useIsDark();
  const local = useEditorSettings(); // line-wrapping only (localStorage)
  const prefs = user?.editor_preferences ?? DEFAULT_EDITOR_PREFERENCES;

  const settings: EditorSettings = {
    fontSize: prefs.font_size,
    keymap: prefs.keymap,
    lineWrapping: local.settings.lineWrapping,
  };
  const dark = resolveDark(prefs.theme, systemDark);

  const update = useCallback(
    (patch: Partial<EditorSettings>) => {
      if (patch.lineWrapping !== undefined) local.update({ lineWrapping: patch.lineWrapping });
      if (patch.fontSize === undefined && patch.keymap === undefined) return;
      const next: EditorPreferences = {
        theme: prefs.theme,
        font_size: patch.fontSize ?? prefs.font_size,
        keymap: patch.keymap ?? prefs.keymap,
      };
      if (user) applyUser({ ...user, editor_preferences: next }); // optimistic
      void putEditorPreferences(next)
        .then((saved) => {
          if (user) applyUser({ ...user, editor_preferences: saved });
        })
        .catch(() => {
          /* keep the optimistic value; the next load reconciles */
        });
    },
    [user, applyUser, prefs, local],
  );

  return { settings, dark, update };
}
