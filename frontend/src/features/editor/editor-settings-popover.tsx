import { Settings } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";

import type { EditorKeymap } from "@/types";

import type { EditorSettings } from "./types";

// Keep in sync with the settings page + the server clamp (10–28, spec 59) so a
// font size chosen in Settings always has a matching option here.
const FONT_SIZES = [10, 12, 14, 16, 18, 20, 24, 28];

const KEYMAPS: { value: EditorKeymap; labelKey: string }[] = [
  { value: "default", labelKey: "settings.keymapDefault" },
  { value: "vim", labelKey: "settings.keymapVim" },
  { value: "emacs", labelKey: "settings.keymapEmacs" },
];

export function EditorSettingsPopover({
  settings,
  onUpdate,
}: {
  settings: EditorSettings;
  onUpdate: (patch: Partial<EditorSettings>) => void;
}) {
  const { t } = useTranslation("editor");
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon" aria-label={t("settings.trigger")}>
          <Settings className="size-4" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="space-y-4">
        <p className="text-sm font-medium">{t("settings.title")}</p>
        <div className="flex items-center justify-between gap-2">
          <label htmlFor="editor-font-size" className="text-sm">
            {t("settings.fontSize")}
          </label>
          <Select
            value={String(settings.fontSize)}
            onValueChange={(v) => onUpdate({ fontSize: Number(v) })}
          >
            <SelectTrigger id="editor-font-size" aria-label={t("settings.fontSize")} className="w-24">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {FONT_SIZES.map((size) => (
                <SelectItem key={size} value={String(size)}>
                  {t("settings.fontSizeUnit", { size })}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex items-center justify-between gap-2">
          <label htmlFor="editor-keymap" className="text-sm">
            {t("settings.keymap")}
          </label>
          <Select
            value={settings.keymap}
            onValueChange={(v) => onUpdate({ keymap: v as EditorKeymap })}
          >
            <SelectTrigger id="editor-keymap" aria-label={t("settings.keymap")} className="w-24">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {KEYMAPS.map((km) => (
                <SelectItem key={km.value} value={km.value}>
                  {t(km.labelKey)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex items-center justify-between gap-2">
          <label htmlFor="editor-wrap" className="text-sm">
            {t("settings.lineWrapping")}
          </label>
          <Switch
            id="editor-wrap"
            aria-label={t("settings.lineWrapping")}
            checked={settings.lineWrapping}
            onCheckedChange={(v) => onUpdate({ lineWrapping: v })}
          />
        </div>
      </PopoverContent>
    </Popover>
  );
}
