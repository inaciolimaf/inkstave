import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { useAuth } from "@/modules/auth";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  DEFAULT_EDITOR_PREFERENCES,
  type EditorKeymap,
  type EditorPreferences,
  type EditorTheme,
} from "@/types";

import { putEditorPreferences } from "./api";
import { errMessage } from "./errMessage";
import { SettingsSection } from "./SettingsSection";

export function EditorPreferencesSection() {
  const { t } = useTranslation("settings");
  const { user, applyUser } = useAuth();
  const prefs = user?.editor_preferences ?? DEFAULT_EDITOR_PREFERENCES;

  async function set(patch: Partial<EditorPreferences>) {
    const next: EditorPreferences = { ...prefs, ...patch };
    if (user) applyUser({ ...user, editor_preferences: next }); // optimistic + live editor update
    try {
      const saved = await putEditorPreferences(next);
      if (user) applyUser({ ...user, editor_preferences: saved });
    } catch (err) {
      toast.error(errMessage(err));
    }
  }

  return (
    <SettingsSection title={t("editor.title")} description={t("editor.description")}>
      <div className="divide-y divide-border">
        <div className="flex items-center justify-between gap-2 py-2">
          <Label htmlFor="pref-theme">{t("editor.theme")}</Label>
          <Select value={prefs.theme} onValueChange={(v) => set({ theme: v as EditorTheme })}>
            <SelectTrigger id="pref-theme" aria-label={t("editor.theme")} className="w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="system">{t("editor.themeSystem")}</SelectItem>
              <SelectItem value="light">{t("editor.themeLight")}</SelectItem>
              <SelectItem value="dark">{t("editor.themeDark")}</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="flex items-center justify-between gap-2 py-2">
          <Label htmlFor="pref-font">{t("editor.fontSize")}</Label>
          <Select value={String(prefs.font_size)} onValueChange={(v) => set({ font_size: Number(v) })}>
            <SelectTrigger id="pref-font" aria-label={t("editor.fontSize")} className="w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {[10, 12, 14, 16, 18, 20, 24, 28].map((s) => (
                <SelectItem key={s} value={String(s)}>
                  {s}px
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex items-center justify-between gap-2 py-2">
          <Label htmlFor="pref-keymap">{t("editor.keymap")}</Label>
          <Select value={prefs.keymap} onValueChange={(v) => set({ keymap: v as EditorKeymap })}>
            <SelectTrigger id="pref-keymap" aria-label={t("editor.keymap")} className="w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="default">{t("editor.keymapDefault")}</SelectItem>
              <SelectItem value="vim">{t("editor.keymapVim")}</SelectItem>
              <SelectItem value="emacs">{t("editor.keymapEmacs")}</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>
    </SettingsSection>
  );
}
