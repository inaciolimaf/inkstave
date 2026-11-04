import { X } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { usePersonalDictionary } from "@/modules/spellcheck";

import { SettingsSection } from "./SettingsSection";

/** The personal spell-check dictionary: the words the user keeps, each one removable (spec 113). */
export function DictionarySection() {
  const { t } = useTranslation("settings");
  const dictionary = usePersonalDictionary();
  const words = dictionary.words ?? [];
  return (
    <SettingsSection title={t("dictionary.title")} description={t("dictionary.description")}>
      {dictionary.words && words.length === 0 && (
        <p className="text-body text-muted-foreground">{t("dictionary.empty")}</p>
      )}
      <ul className="flex flex-wrap gap-2">
        {words.map((word) => (
          <li key={word}>
            <span className="inline-flex items-center gap-1 rounded border py-0.5 pl-2 pr-0.5 font-mono text-small">
              {word}
              <Button
                variant="ghost"
                size="icon"
                className="size-7"
                aria-label={t("dictionary.removeWord", { word })}
                onClick={() => dictionary.remove(word)}
              >
                <X aria-hidden="true" className="size-3.5" />
              </Button>
            </span>
          </li>
        ))}
      </ul>
    </SettingsSection>
  );
}
