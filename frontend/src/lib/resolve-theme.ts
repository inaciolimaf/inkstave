import type { EditorTheme } from "@/types";

/** Resolve the editor's effective dark mode from the theme preference (spec 59):
 * an explicit light/dark wins; "system" follows the OS setting. */
export function resolveDark(theme: EditorTheme, systemDark: boolean): boolean {
  if (theme === "dark") return true;
  if (theme === "light") return false;
  return systemDark;
}
