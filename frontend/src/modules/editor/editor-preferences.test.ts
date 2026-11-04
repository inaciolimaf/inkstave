import { renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { EditorPreferences, UserPublic } from "@/types";
import { putEditorPreferences } from "@/modules/settings/api";

import { keymapExtension } from "./keymap-extension";
import { resolveDark } from "@/lib/resolve-theme";
import { useEditorPreferences } from "./use-editor-preferences";

// Mock the hook's data sources so the mapping test is pure and fast.
let mockUser: UserPublic | null = null;
let mockSystemDark = false;
vi.mock("@/modules/auth/auth-context", () => ({
  useAuth: () => ({ user: mockUser, applyUser: vi.fn() }),
}));
vi.mock("@/lib/use-is-dark", () => ({ useIsDark: () => mockSystemDark }));
vi.mock("@/modules/settings/api", () => ({ putEditorPreferences: vi.fn() }));

describe("resolveDark", () => {
  it("honours explicit light/dark and follows the system for 'system'", () => {
    expect(resolveDark("dark", false)).toBe(true);
    expect(resolveDark("light", true)).toBe(false);
    expect(resolveDark("system", true)).toBe(true);
    expect(resolveDark("system", false)).toBe(false);
  });
});

describe("keymapExtension", () => {
  it("returns just the base keymap for default, and prepends vim/emacs otherwise", () => {
    // default → a single facet provider; vim/emacs → [handler, base].
    expect(Array.isArray(keymapExtension("default"))).toBe(false);
    const vimExt = keymapExtension("vim");
    const emacsExt = keymapExtension("emacs");
    expect(Array.isArray(vimExt) && vimExt.length).toBe(2);
    expect(Array.isArray(emacsExt) && emacsExt.length).toBe(2);
  });
});

describe("useEditorPreferences", () => {
  function userWith(prefs: EditorPreferences): UserPublic {
    return {
      id: "u1",
      email: "a@b.c",
      display_name: "A",
      is_admin: false,
      email_confirmed: true,
      created_at: "2026-01-01T00:00:00Z",
      editor_preferences: prefs,
    };
  }

  beforeEach(() => {
    localStorage.clear();
    mockUser = null;
    mockSystemDark = false;
  });
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("maps stored server prefs → CodeMirror EditorSettings (theme/font/keymap)", () => {
    mockUser = userWith({ theme: "dark", font_size: 18, keymap: "vim", autocomplete: true });
    const { result } = renderHook(() => useEditorPreferences());
    expect(result.current.settings.fontSize).toBe(18);
    expect(result.current.settings.keymap).toBe("vim");
    expect(result.current.dark).toBe(true);
  });

  it("resolves the 'system' theme from the host dark mode", () => {
    mockUser = userWith({ theme: "system", font_size: 12, keymap: "emacs", autocomplete: true });
    mockSystemDark = true;
    const { result } = renderHook(() => useEditorPreferences());
    expect(result.current.settings.keymap).toBe("emacs");
    expect(result.current.dark).toBe(true);
  });

  it("falls back to default prefs when the user has none", () => {
    mockUser = null;
    const { result } = renderHook(() => useEditorPreferences());
    expect(result.current.settings.fontSize).toBe(14);
    expect(result.current.settings.keymap).toBe("default");
    expect(result.current.dark).toBe(false); // 'system' theme, light host
    expect(result.current.settings.autocomplete).toBe(true);
  });

  it("maps the autocomplete switch of the account (spec 112)", () => {
    mockUser = userWith({ theme: "system", font_size: 14, keymap: "default", autocomplete: false });
    const { result } = renderHook(() => useEditorPreferences());
    expect(result.current.settings.autocomplete).toBe(false);
  });

  it("saves the autocomplete switch with the other preferences, keeping them", async () => {
    mockUser = userWith({ theme: "dark", font_size: 18, keymap: "vim", autocomplete: true });
    vi.mocked(putEditorPreferences).mockResolvedValueOnce({
      ...mockUser.editor_preferences,
      autocomplete: false,
    });
    const { result } = renderHook(() => useEditorPreferences());
    result.current.update({ autocomplete: false });
    expect(putEditorPreferences).toHaveBeenCalledWith({
      theme: "dark",
      font_size: 18,
      keymap: "vim",
      autocomplete: false,
    });
  });
});
