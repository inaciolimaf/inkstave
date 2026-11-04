import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";

export type NewProjectSpelling = "en-US" | "pt-BR";

const OPTIONS: { value: NewProjectSpelling; labelKey: string }[] = [
  { value: "en-US", labelKey: "create.spelling.enUS" },
  { value: "pt-BR", labelKey: "create.spelling.ptBR" },
];

/** The spell-check language picked when a project is created; the editor's menu changes it later (spec 113). */
export function SpellcheckLanguageField({
  value,
  onChange,
}: {
  value: NewProjectSpelling;
  onChange: (v: NewProjectSpelling) => void;
}) {
  const { t } = useTranslation("projects");
  return (
    <fieldset className="space-y-2">
      <legend className="text-small font-medium">{t("create.spelling.label")}</legend>
      <div className="flex flex-wrap gap-2">
        {OPTIONS.map((option) => (
          <label
            key={option.value}
            className={cn(
              "flex min-h-11 cursor-pointer items-center gap-2 rounded-md border px-3 text-small",
              "focus-within:ring-2 focus-within:ring-ring",
              value === option.value ? "border-foreground" : "border-border-strong",
            )}
          >
            <input
              type="radio"
              name="spellcheck-language"
              value={option.value}
              checked={value === option.value}
              onChange={() => onChange(option.value)}
            />
            {t(option.labelKey)}
          </label>
        ))}
      </div>
      <p className="text-small text-muted-foreground">{t("create.spelling.hint")}</p>
    </fieldset>
  );
}
