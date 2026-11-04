/** The microphone beside the agent's send button, with its language and "send after" options (spec 115). */
import { Check, ChevronDown, Mic } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";

import type { DictationLang } from "./speech";
import type { DictationApi } from "./use-dictation";

const LANGS: { lang: DictationLang; key: "lang.en" | "lang.pt" }[] = [
  { lang: "en-US", key: "lang.en" },
  { lang: "pt-BR", key: "lang.pt" },
];
// Phone targets are 44 px; the desktop window keeps the compact size.
const TOUCH_SIZE = "size-11 md:size-9";

/** A check mark on the chosen item; the text is what a screen reader announces. */
function Choice({ checked, children }: { checked: boolean; children: string }) {
  return (
    <>
      <Check aria-hidden="true" className={cn("size-4", !checked && "invisible")} />
      {children}
    </>
  );
}

function DictationOptions({ dictation }: { dictation: DictationApi }) {
  const { t } = useTranslation("agent");
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          size="icon"
          variant="ghost"
          className={TOUCH_SIZE}
          aria-label={t("dictation.options")}
        >
          <ChevronDown className="size-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {LANGS.map(({ lang, key }) => (
          <DropdownMenuItem key={lang} onClick={() => dictation.setLang(lang)}>
            <Choice checked={dictation.lang === lang}>{t(`dictation.${key}`)}</Choice>
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={() => dictation.setSendAfter(!dictation.sendAfter)}>
          <Choice checked={dictation.sendAfter}>{t("dictation.sendAfter")}</Choice>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** Renders nothing where the browser has no speech recognition, so the composer is unchanged. */
export function DictateButton({ dictation, disabled }: { dictation: DictationApi; disabled: boolean }) {
  const { t } = useTranslation("agent");
  if (!dictation.supported) return null;
  const listening = dictation.state === "listening";
  return (
    <div className="flex shrink-0 items-center">
      <Button
        type="button"
        size="icon"
        variant="outline"
        className={cn(TOUCH_SIZE, listening && "animate-pulse border-foreground motion-reduce:animate-none")}
        onClick={dictation.toggle}
        disabled={disabled}
        aria-pressed={listening}
        aria-keyshortcuts="Control+Shift+M Meta+Shift+M"
        aria-label={t(listening ? "dictation.stop" : "dictation.start")}
      >
        <Mic className="size-4" />
      </Button>
      <DictationOptions dictation={dictation} />
    </div>
  );
}
