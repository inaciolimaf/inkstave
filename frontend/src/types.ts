/** App-wide API shapes, named from the generated contract (specs 06-08, 59). */
import type { Schemas } from "@/api/models";

export type EditorTheme = Schemas["EditorPreferences"]["theme"];
export type EditorKeymap = Schemas["EditorPreferences"]["keymap"];

export type EditorPreferences = Schemas["EditorPreferences"];

export const DEFAULT_EDITOR_PREFERENCES: EditorPreferences = {
  theme: "system",
  font_size: 14,
  keymap: "default",
  autocomplete: true,
};

export type UserPublic = Schemas["UserMe"];

export type TokenPair = Schemas["TokenPair"];

/** Field-scoped validation errors keyed by field name (from a 422 envelope). */
export type FieldErrors = Record<string, string>;
