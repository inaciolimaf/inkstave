import { toast } from "sonner";

import { useAuth } from "@/auth/auth-context";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  DEFAULT_EDITOR_PREFERENCES,
  type EditorKeymap,
  type EditorPreferences,
  type EditorTheme,
} from "@/types";

import { putEditorPreferences } from "./api";
import { errMessage } from "./errMessage";

export function EditorPreferencesSection() {
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
    <Card>
      <CardHeader>
        <CardTitle>Editor preferences</CardTitle>
        <CardDescription>Applied to your editor immediately and saved to your account.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center justify-between gap-2">
          <Label htmlFor="pref-theme">Theme</Label>
          <Select value={prefs.theme} onValueChange={(v) => set({ theme: v as EditorTheme })}>
            <SelectTrigger id="pref-theme" aria-label="Theme" className="w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="system">System</SelectItem>
              <SelectItem value="light">Light</SelectItem>
              <SelectItem value="dark">Dark</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="flex items-center justify-between gap-2">
          <Label htmlFor="pref-font">Font size</Label>
          <Select
            value={String(prefs.font_size)}
            onValueChange={(v) => set({ font_size: Number(v) })}
          >
            <SelectTrigger id="pref-font" aria-label="Font size" className="w-40">
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
        <div className="flex items-center justify-between gap-2">
          <Label htmlFor="pref-keymap">Keymap</Label>
          <Select value={prefs.keymap} onValueChange={(v) => set({ keymap: v as EditorKeymap })}>
            <SelectTrigger id="pref-keymap" aria-label="Keymap" className="w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="default">Default</SelectItem>
              <SelectItem value="vim">Vim</SelectItem>
              <SelectItem value="emacs">Emacs</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </CardContent>
    </Card>
  );
}
