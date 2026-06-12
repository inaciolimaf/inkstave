/** TypeScript mirrors of the backend Pydantic shapes (specs 06-08, 59). */

export type EditorTheme = "light" | "dark" | "system";
export type EditorKeymap = "default" | "vim" | "emacs";

export interface EditorPreferences {
  theme: EditorTheme;
  font_size: number;
  keymap: EditorKeymap;
}

export const DEFAULT_EDITOR_PREFERENCES: EditorPreferences = {
  theme: "system",
  font_size: 14,
  keymap: "default",
};

export interface UserPublic {
  id: string;
  email: string;
  display_name: string;
  is_admin: boolean;
  email_confirmed: boolean;
  created_at: string;
  // Present on the /users/me self-view (spec 59); optional elsewhere.
  avatar_url?: string | null;
  editor_preferences?: EditorPreferences;
  pending_email?: string | null;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  expires_in: number;
}

/** Field-scoped validation errors keyed by field name (from a 422 envelope). */
export type FieldErrors = Record<string, string>;
