/** Composer, run controls, and error state (spec 46). */
import { Loader2, Send, Square } from "lucide-react";
import type { KeyboardEvent } from "react";
import { useTranslation } from "react-i18next";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

export function AgentComposer({
  value,
  onChange,
  onSend,
  disabled,
}: {
  value: string;
  onChange: (v: string) => void;
  onSend: (text: string) => void;
  disabled: boolean;
}) {
  const { t } = useTranslation("agent");
  const submit = () => {
    const text = value.trim();
    if (text && !disabled) onSend(text);
  };
  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };
  return (
    <div className="flex items-end gap-2 p-2">
      <Textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={onKeyDown}
        disabled={disabled}
        rows={2}
        placeholder={t("composer.placeholder")}
        aria-label={t("composer.messageLabel")}
        className="resize-none"
      />
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              size="icon"
              onClick={submit}
              disabled={disabled || !value.trim()}
              aria-label={t("composer.sendLabel")}
            >
              {/* Spinner while a run is starting/streaming (disabled); Send otherwise. */}
              {disabled ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
            </Button>
          </TooltipTrigger>
          <TooltipContent>{t("composer.sendTooltip")}</TooltipContent>
        </Tooltip>
      </TooltipProvider>
    </div>
  );
}

export function RunControls({ onStop }: { onStop: () => void }) {
  const { t } = useTranslation("agent");
  return (
    <div className="flex justify-center px-2 pt-2">
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={onStop}
              aria-label={t("run.stopLabel")}
            >
              <Square className="size-3.5" />
              {t("run.stop")}
            </Button>
          </TooltipTrigger>
          <TooltipContent>{t("run.stop")}</TooltipContent>
        </Tooltip>
      </TooltipProvider>
    </div>
  );
}

const FRIENDLY_TITLE_KEYS: Record<string, string> = {
  transport: "error.titles.transport",
  internal: "error.titles.internal",
  llm_error: "error.titles.llm_error",
  rate_limited: "error.titles.rate_limited",
  agent_rate_limited: "error.titles.agent_rate_limited",
  budget_exceeded: "error.titles.budget_exceeded",
  agent_budget_exceeded: "error.titles.agent_budget_exceeded",
  cancelled: "error.titles.cancelled",
  timeout: "error.titles.timeout",
};

export function AgentErrorState({
  error,
  onRetry,
}: {
  error: { code: string; message: string; retryable: boolean };
  onRetry: () => void;
}) {
  const { t } = useTranslation("agent");
  const titleKey = FRIENDLY_TITLE_KEYS[error.code];
  return (
    <Alert variant="destructive" className="m-2">
      <AlertTitle>{titleKey ? t(titleKey) : t("error.generic")}</AlertTitle>
      <AlertDescription className="flex items-center justify-between gap-2">
        <span>{error.message}</span>
        {error.retryable && (
          <Button size="sm" variant="outline" onClick={onRetry}>
            {t("error.retry")}
          </Button>
        )}
      </AlertDescription>
    </Alert>
  );
}
