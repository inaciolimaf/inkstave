/** The agent: a floating window that blocks nothing behind it, or a sheet on a phone (specs 46, 107). */
import { ChevronDown, Loader2, MessageSquarePlus, Sparkles, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

import { DiffReviewDialog } from "@/modules/diff-review";
import type { DocumentBridge } from "@/modules/diff-review";

import { AgentComposer, AgentErrorState, RunControls } from "./controls";
import { FileOpCard } from "./file-op-card";
import { AgentTranscript } from "./transcript";
import { withQuote, type AgentQuote, type AgentRequest } from "./quote";
import { useAgentChat } from "./useAgentChat";

const ACTIVE_PHASES = ["starting", "streaming", "stopping"];

function EmptyState({ onPick }: { onPick: (text: string) => void }) {
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

function PanelHeader({
  titleId,
  title,
  chat,
  onMinimize,
}: {
  titleId: string;
  title: string;
  chat: ReturnType<typeof useAgentChat>;
  onMinimize: () => void;
}) {
  const { t } = useTranslation("agent");
  return (
    <div className="flex items-center gap-1 border-b py-1.5 pl-3 pr-1.5">
      <h2 id={titleId} className="min-w-0 flex-1 truncate font-serif text-heading font-medium">
        {title}
      </h2>
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
function Launcher({ busy, onOpen }: { busy: boolean; onOpen: () => void }) {
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

function Conversation({
  chat,
  onPickExample,
  onReviewProposal,
  projectId,
}: {
  chat: ReturnType<typeof useAgentChat>;
  projectId: string;
  onPickExample: (text: string) => void;
  onReviewProposal: (proposalId: string) => void;
}) {
  const { t } = useTranslation("agent");
  const sessionId = chat.activeSessionId;
  if (chat.run.items.length > 0) {
    return (
      <AgentTranscript
        items={chat.run.items}
        loading={chat.transcriptLoading}
        onReviewProposal={onReviewProposal}
        renderFileOp={(item) =>
          sessionId && <FileOpCard projectId={projectId} sessionId={sessionId} op={item} />
        }
      />
    );
  }
  if (!chat.transcriptLoading) return <EmptyState onPick={onPickExample} />;
  return (
    <div
      className="flex-1 space-y-2 p-4"
      role="status"
      aria-busy="true"
      aria-label={t("loadingConversation")}
    >
      <Skeleton className="h-4 w-2/3" />
      <Skeleton className="h-4 w-1/2" />
      <Skeleton className="h-4 w-3/4" />
    </div>
  );
}

/** Each request is a new object, so the same selection can be asked about twice, and handled once. */
function useEditorRequest(
  request: AgentRequest | null,
  send: (text: string) => Promise<boolean>,
  setQuote: (quote: AgentQuote) => void,
) {
  const handled = useRef<AgentRequest | null>(null);
  useEffect(() => {
    if (!request || handled.current === request) return;
    handled.current = request;
    if (request.quote) setQuote(request.quote);
    if (request.send) void send(request.send);
  }, [request, send, setQuote]);
}

export function AgentPanel({
  projectId,
  open,
  onOpenChange,
  onReviewProposal,
  documentBridge,
  onBeforeSend,
  request = null,
}: {
  projectId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onReviewProposal: (proposalId: string) => void;
  documentBridge?: DocumentBridge;
  /** Flush open collab docs before a run so the agent reads current text (spec 28/42). */
  onBeforeSend?: () => Promise<void>;
  /** Something the editor asked for: a selection to discuss, or a problem to fix. */
  request?: AgentRequest | null;
}) {
  const { t } = useTranslation("agent");
  const chat = useAgentChat(projectId, onBeforeSend);
  const [composerText, setComposerText] = useState("");
  const [quote, setQuote] = useState<AgentQuote | null>(null);
  const [reviewId, setReviewId] = useState<string | null>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const active = ACTIVE_PHASES.includes(chat.run.phase);

  useEffect(() => {
    if (open) composerRef.current?.focus();
  }, [open, request]);

  useEditorRequest(request, chat.send, setQuote);

  const handleReview = (proposalId: string) => {
    onReviewProposal(proposalId);
    if (documentBridge) setReviewId(proposalId);
  };

  const activeSession = chat.sessions.find((s) => s.id === chat.activeSessionId);
  const title = activeSession?.title ?? t("newChat");
  const titleId = `agent-title-${projectId}`;

  return (
    <>
      {!open && <Launcher busy={active} onOpen={() => onOpenChange(true)} />}
      <section
        role="dialog"
        aria-modal="false"
        aria-labelledby={titleId}
        aria-description={t("description")}
        onKeyDown={(e) => {
          if (e.key === "Escape" && e.currentTarget.contains(e.target as Node)) onOpenChange(false);
        }}
        className={cn(
          "fixed inset-x-0 bottom-12 top-12 z-40 flex-col border-t bg-background",
          "md:bottom-4 md:left-auto md:right-4 md:top-auto md:h-[min(34rem,calc(100dvh-6rem))] md:w-[26rem]",
          "md:overflow-hidden md:rounded-lg md:border md:border-control-edge md:shadow-xl",
          open ? "flex" : "hidden",
        )}
      >
        <PanelHeader titleId={titleId} title={title} chat={chat} onMinimize={() => onOpenChange(false)} />
        <Conversation
          chat={chat}
          projectId={projectId}
          onPickExample={setComposerText}
          onReviewProposal={handleReview}
        />

        {chat.run.error && <AgentErrorState error={chat.run.error} onRetry={chat.retry} />}

        <div className="border-t">
          {active && <RunControls canStop={Boolean(chat.run.runId)} onStop={() => void chat.stop()} />}
          {quote && <QuoteChip quote={quote} onClear={() => setQuote(null)} />}
          <AgentComposer
            ref={composerRef}
            value={composerText}
            onChange={setComposerText}
            disabled={active}
            onSend={(text) => {
              const sentQuote = quote;
              setComposerText("");
              setQuote(null);
              void chat.send(withQuote(text, sentQuote)).then((accepted) => {
                if (accepted) return;
                setComposerText(text);
                setQuote(sentQuote);
              });
            }}
          />
        </div>
      </section>

      {documentBridge && chat.activeSessionId && (
        <DiffReviewDialog
          projectId={projectId}
          sessionId={chat.activeSessionId}
          proposalId={reviewId}
          bridge={documentBridge}
          open={reviewId !== null}
          onOpenChange={(o) => !o && setReviewId(null)}
        />
      )}
    </>
  );
}
