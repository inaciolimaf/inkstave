/** The agent: a floating window that blocks nothing behind it, or a sheet on a phone (specs 46, 107). */
import { type CSSProperties, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

import { DiffReviewDialog } from "@/modules/diff-review";
import type { DocumentBridge } from "@/modules/diff-review";

import { AgentErrorState } from "./controls";
import { FileOpCard } from "./file-op-card";
import { AgentTranscript } from "./transcript";
import { EmptyState, Launcher, PanelFooter, PanelHeader } from "./panel-parts";
import type { AgentQuote, AgentRequest } from "./quote";
import { useAgentChat } from "./useAgentChat";
import { useWindowSize, type WindowSize } from "./use-window-size";
import { WindowResizeHandles } from "./window-resize-handles";

const ACTIVE_PHASES = ["starting", "streaming", "stopping"];

/** Variables, not a width: on a phone the window is a sheet and must ignore a size set on the desktop. */
function sizeVars(size: WindowSize | null) {
  if (!size) return undefined;
  return { "--agent-w": `${size.width}px`, "--agent-h": `${size.height}px` } as CSSProperties;
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
  const windowSize = useWindowSize();
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
          "md:bottom-4 md:left-auto md:right-4 md:top-auto",
          "md:h-[var(--agent-h,min(34rem,calc(100dvh-6rem)))] md:w-[var(--agent-w,26rem)]",
          "md:max-h-[calc(100dvh-6rem)] md:max-w-[calc(100dvw-2rem)]",
          "md:overflow-hidden md:rounded-lg md:border md:border-control-edge md:shadow-xl",
          open ? "flex" : "hidden",
        )}
        style={sizeVars(windowSize.size)}
      >
        <WindowResizeHandles resize={windowSize} />
        <PanelHeader
          titleId={titleId}
          title={title}
          chat={chat}
          onMinimize={() => onOpenChange(false)}
          large={windowSize.large}
          onToggleLarge={windowSize.toggleLarge}
        />
        <Conversation
          chat={chat}
          projectId={projectId}
          onPickExample={setComposerText}
          onReviewProposal={handleReview}
        />

        {chat.run.error && <AgentErrorState error={chat.run.error} onRetry={chat.retry} />}

        <PanelFooter
          chat={chat}
          active={active}
          text={composerText}
          onTextChange={setComposerText}
          quote={quote}
          onQuoteChange={setQuote}
          composerRef={composerRef}
        />
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
