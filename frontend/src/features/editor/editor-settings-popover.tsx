import { Settings } from "lucide-react";

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

import type { EditorSettings } from "./types";

const FONT_SIZES = [10, 12, 14, 16, 18, 20, 22, 24];

export function EditorSettingsPopover({
  settings,
  onUpdate,
}: {
  settings: EditorSettings;
  onUpdate: (patch: Partial<EditorSettings>) => void;
}) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon" aria-label="Editor settings">
          <Settings className="size-4" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="space-y-4">
        <p className="text-sm font-medium">Editor settings</p>
        <div className="flex items-center justify-between gap-2">
          <label htmlFor="editor-font-size" className="text-sm">
            Font size
          </label>
          <Select
            value={String(settings.fontSize)}
            onValueChange={(v) => onUpdate({ fontSize: Number(v) })}
          >
            <SelectTrigger id="editor-font-size" aria-label="Font size" className="w-24">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {FONT_SIZES.map((size) => (
                <SelectItem key={size} value={String(size)}>
                  {size}px
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex items-center justify-between gap-2">
          <label htmlFor="editor-wrap" className="text-sm">
            Line wrapping
          </label>
          <Switch
            id="editor-wrap"
            aria-label="Line wrapping"
            checked={settings.lineWrapping}
            onCheckedChange={(v) => onUpdate({ lineWrapping: v })}
          />
        </div>
      </PopoverContent>
    </Popover>
  );
}
