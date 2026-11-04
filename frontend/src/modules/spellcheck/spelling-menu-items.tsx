import { Check } from "lucide-react";
import { useTranslation } from "react-i18next";

import { DropdownMenuItem, DropdownMenuSeparator } from "@/components/ui/dropdown-menu";

import { useSpellLanguage } from "./use-spellcheck";
import { SPELL_LANGUAGES, type SpellLanguage } from "./types";

const LABEL_KEYS: Record<SpellLanguage, string> = {
  off: "spellcheck.language.off",
  "en-US": "spellcheck.language.enUS",
  "pt-BR": "spellcheck.language.ptBR",
};

/** "Spelling: English / Português (Brasil) / Off", for the editor bar's menu (spec 113). */
export function SpellingMenuItems({ projectId, readOnly }: { projectId: string; readOnly: boolean }) {
  const { t } = useTranslation("editor");
  const { language, setLanguage, saving } = useSpellLanguage(projectId);
  return (
    <>
      <div role="presentation" className="px-2 py-1.5 text-small text-muted-foreground">
        {t("spellcheck.menuLabel")}
      </div>
      {SPELL_LANGUAGES.map((option) => (
        <DropdownMenuItem
          key={option}
          disabled={readOnly || saving}
          aria-current={option === language ? "true" : undefined}
          onSelect={() => setLanguage(option)}
        >
          <Check aria-hidden="true" className={option === language ? "size-4" : "size-4 opacity-0"} />
          {t(LABEL_KEYS[option])}
        </DropdownMenuItem>
      ))}
      <DropdownMenuSeparator />
    </>
  );
}
