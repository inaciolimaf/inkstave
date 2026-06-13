import { useEffect } from "react";

import { useAuth } from "@/auth/auth-context";
import { DEFAULT_EDITOR_PREFERENCES } from "@/types";

import { resolveDark } from "./resolve-theme";
import { useIsDark } from "./use-is-dark";

/**
 * Applies the user's theme preference to the document root (spec 59): toggles
 * the Tailwind `dark` class on <html> so the whole app — not just the CodeMirror
 * editor — follows the chosen theme. "system" tracks the OS setting. Mounted once
 * at the app root; reacts live to preference changes and OS-theme changes.
 */
export function useApplyTheme(): void {
  const { user } = useAuth();
  const systemDark = useIsDark();
  const theme = user?.editor_preferences?.theme ?? DEFAULT_EDITOR_PREFERENCES.theme;
  const dark = resolveDark(theme, systemDark);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
  }, [dark]);
}
