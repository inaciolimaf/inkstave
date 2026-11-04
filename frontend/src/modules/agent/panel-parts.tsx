/** The pieces of the agent window around the conversation. */
import { ChevronDown, Loader2, Maximize2, MessageSquarePlus, Minimize2, Sparkles, X } from "lucide-react";
import type { Ref } from "react";
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

import { AgentComposer, RunControls } from "./controls";
import type { AgentQuote } from "./quote";
import { withQuote } from "./quote";
import { RunStatus } from "./run-status";
import type { useAgentChat } from "./useAgentChat";

export function EmptyState({ onPick }: { onPick: (text: string) => void }) {
  const { t } = useTranslation("agent");
  const examples = [t("empty.example1"), t("empty.example2"), t("empty.example3")];
  return (
    <div className="flex-1 space-y-3 p-4 text-body text-muted-foreground">
      <p>{t("empty.intro")}</p>
      <div className="flex flex-col divide-y border-y">
        {examples.map((ex) => (
          <button
            key={ex}
            type="button"
            onClick={() => onPick(ex)}
            className="py-2 text-left text-small hover:text-foreground"
          >
            {ex}
          </button>
        ))}
      </div>
    </div>
  );
}

export type SideView = "agent" | "chat";

/** The agent and the project chat share one window; this switch picks which one it shows (spec 117). */
export function SideSwitch({ view, onChange }: { view: SideView; onChange: (view: SideView) => void }) {
  const { t } = useTranslation(["agent", "discussion"]);
  const option = (value: SideView, label: string) => (
    <button
      type="button"
      aria-pressed={view === value}
      onClick={() => onChange(value)}
      className={cn(
        "h-7 rounded px-2.5 text-small font-medium",
        view === value ? "bg-accent text-foreground" : "text-muted-foreground hover:text-foreground",
      )}
    >
      {label}
    </button>
  );
  return (
    <div
      role="group"
      aria-label={t("agent:sideSwitch.label")}
      className="flex min-w-0 flex-1 items-center gap-1"
    >
      {option("agent", t("agent:sideSwitch.agent"))}
      {option("chat", t("discussion:tabs.chat"))}
    </div>
  );
}

export function PanelHeader({
  titleId,
  title,
  chat,
  onMinimize,
  large,
  onToggleLarge,
  side,
}: {
  titleId: string;
  title: string;
  chat: ReturnType<typeof useAgentChat>;
  onMinimize: () => void;
  large: boolean;
  onToggleLarge: () => void;
  /** Present when the window also holds the project chat: the switch replaces the title. */
  side?: { view: SideView; onViewChange: (view: SideView) => void };
}) {
  const { t } = useTranslation("agent");
  const agentView = side === undefined || side.view === "agent";
  return (
    <div className="flex items-center gap-1 border-b py-1.5 pl-3 pr-1.5 md:pl-6">
      {side ? (
        <SideSwitch view={side.view} onChange={side.onViewChange} />
      ) : (
        <h2 id={titleId} className="min-w-0 flex-1 truncate font-serif text-heading font-medium">
          {title}
        </h2>
      )}
      {agentView && (
        <>
          <Button
            size="icon"
            variant="ghost"
            className="size-7"
            aria-label={t("newChat")}
            onClick={() => void chat.newChat()}
          >
            <MessageSquarePlus className="size-4" />
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button size="sm" variant="ghost" className="h-7">
                {t("sessions")}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => void chat.newChat()}>{t("newChat")}</DropdownMenuItem>
              {chat.sessions.length > 0 && <DropdownMenuSeparator />}
              {chat.sessions.map((s) => (
                <DropdownMenuItem key={s.id} onClick={() => void chat.selectSession(s.id)}>
                  {s.title ?? t("untitledChat")}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        </>
      )}
      <Button
        size="icon"
        variant="ghost"
        className="hidden size-7 md:inline-flex"
        aria-label={t(large ? "window.shrink" : "window.enlarge")}
        onClick={onToggleLarge}
      >
        {large ? <Minimize2 className="size-4" /> : <Maximize2 className="size-4" />}
      </Button>
      <Button size="icon" variant="ghost" className="size-7" aria-label={t("minimize")} onClick={onMinimize}>
        <ChevronDown className="size-4" />
      </Button>
    </div>
  );
}

function QuoteChip({ quote, onClear }: { quote: AgentQuote; onClear: () => void }) {
  const { t } = useTranslation("agent");
  return (
    <div className="px-2 pt-2">
      <span className="inline-flex max-w-full items-center gap-1 rounded bg-accent py-0.5 pl-2 pr-1 font-mono text-small">
        <span className="truncate">
          {t("quote.label", { path: quote.path, from: quote.fromLine, to: quote.toLine })}
        </span>
        <button
          type="button"
          aria-label={t("quote.remove")}
          onClick={onClear}
          className="shrink-0 rounded p-0.5 hover:bg-border"
        >
          <X aria-hidden="true" className="size-3.5" />
        </button>
      </span>
    </div>
  );
}

/** The way back to a folded window. On a phone the tabs under the text do this job. */
export function Launcher({ busy, onOpen }: { busy: boolean; onOpen: () => void }) {
  const { t } = useTranslation("agent");
  return (
    <button
      type="button"
      onClick={onOpen}
      className="fixed bottom-4 right-4 z-40 hidden items-center gap-2 rounded-full border border-control-edge bg-background px-4 py-2 text-body font-semibold shadow-lg hover:bg-accent md:inline-flex"
    >
      {busy ? (
        <Loader2 aria-hidden="true" className="size-4 animate-spin" />
      ) : (
        <Sparkles aria-hidden="true" className="size-4" />
      )}
      {t("launcher")}
      {busy && <span className="sr-only">{t("working")}</span>}
    </button>
  );
}

export function PanelFooter({
  chat,
  active,
  text,
  onTextChange,
  quote,
  onQuoteChange,
  composerRef,
}: {
  chat: ReturnType<typeof useAgentChat>;
  active: boolean;
  text: string;
  onTextChange: (text: string) => void;
  quote: AgentQuote | null;
  onQuoteChange: (quote: AgentQuote | null) => void;
  composerRef: Ref<HTMLTextAreaElement>;
}) {
  return (
    <div className="border-t">
      {active && (
        <div className="flex items-center justify-between gap-2 px-2 pt-2">
          <RunStatus run={chat.run} />
          <RunControls canStop={Boolean(chat.run.runId)} onStop={() => void chat.stop()} />
        </div>
      )}
      {quote && <QuoteChip quote={quote} onClear={() => onQuoteChange(null)} />}
      <AgentComposer
        ref={composerRef}
        value={text}
        onChange={onTextChange}
        disabled={active}
        onSend={(text) => {
          const sentQuote = quote;
          onTextChange("");
          onQuoteChange(null);
          void chat.send(withQuote(text, sentQuote)).then((accepted) => {
            if (accepted) return;
            onTextChange(text);
            onQuoteChange(sentQuote);
          });
        }}
      />
    </div>
  );
}
