/** Composer, run controls, and error state (spec 46). */
import { Loader2, Send, Square } from "lucide-react";
import type { KeyboardEvent } from "react";

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
        placeholder="Ask the agent to read or edit the project…"
        aria-label="Message the agent"
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
              aria-label="Send message"
            >
              {/* Spinner while a run is starting/streaming (disabled); Send otherwise. */}
              {disabled ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
            </Button>
          </TooltipTrigger>
          <TooltipContent>Send (Enter)</TooltipContent>
        </Tooltip>
      </TooltipProvider>
    </div>
  );
}

export function RunControls({ onStop }: { onStop: () => void }) {
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
              aria-label="Stop the run"
            >
              <Square className="size-3.5" />
              Stop
            </Button>
          </TooltipTrigger>
          <TooltipContent>Stop</TooltipContent>
        </Tooltip>
      </TooltipProvider>
    </div>
  );
}

const FRIENDLY_TITLES: Record<string, string> = {
  transport: "Connection lost",
  internal: "Run failed",
  llm_error: "AI service unavailable",
  rate_limited: "Rate limit reached",
  agent_rate_limited: "Rate limit reached",
  budget_exceeded: "Budget exceeded",
  agent_budget_exceeded: "Budget reached",
  cancelled: "Run cancelled",
};

export function AgentErrorState({
  error,
  onRetry,
}: {
  error: { code: string; message: string; retryable: boolean };
  onRetry: () => void;
}) {
  return (
    <Alert variant="destructive" className="m-2">
      <AlertTitle>{FRIENDLY_TITLES[error.code] ?? "Error"}</AlertTitle>
      <AlertDescription className="flex items-center justify-between gap-2">
        <span>{error.message}</span>
        {error.retryable && (
          <Button size="sm" variant="outline" onClick={onRetry}>
            Retry
          </Button>
        )}
      </AlertDescription>
    </Alert>
  );
}
