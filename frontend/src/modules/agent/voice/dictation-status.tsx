/** What dictation shows above the message box: the consent notice, the words being heard, or an error. */
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";

import type { DictationApi } from "./use-dictation";

function ConsentNotice({ onAnswer }: { onAnswer: (accept: boolean) => void }) {
  const { t } = useTranslation("agent");
  return (
    <div className="mx-2 mt-2 space-y-2 rounded border p-2 text-small">
      <p>{t("dictation.consent.text")}</p>
      <div className="flex justify-end gap-2">
        <Button size="sm" variant="outline" onClick={() => onAnswer(false)}>
          {t("dictation.consent.cancel")}
        </Button>
        <Button size="sm" onClick={() => onAnswer(true)}>
          {t("dictation.consent.accept")}
        </Button>
      </div>
    </div>
  );
}

/** Interim words are muted: they may still change, and the final words replace them. */
export function DictationStatus({ dictation }: { dictation: DictationApi }) {
  const { t } = useTranslation("agent");
  if (dictation.state === "asking-consent") return <ConsentNotice onAnswer={dictation.answerConsent} />;
  if (dictation.state === "listening") {
    return (
      <p className="px-3 pt-2 text-small text-muted-foreground" aria-live="polite">
        <span className="font-medium text-foreground">{t("dictation.listening")}</span>
        {dictation.interim && <span className="italic"> {dictation.interim}</span>}
      </p>
    );
  }
  if (dictation.error) {
    return (
      <p role="alert" className="px-3 pt-2 text-small text-destructive">
        {t(`dictation.errors.${dictation.error}`)}
      </p>
    );
  }
  return null;
}
