/** The dockable AI agent chat panel (spec 46). */
import { MessageSquarePlus } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";

import { DiffReviewDialog } from "@/features/diff-review/DiffReviewDialog";
import type { DocumentBridge } from "@/features/diff-review/types";

import { AgentComposer, AgentErrorState, RunControls } from "./controls";
import { AgentTranscript } from "./transcript";
import { useAgentChat } from "./useAgentChat";

const ACTIVE_PHASES = ["starting", "streaming", "stopping"];

// Spec 46 §5.4: the panel is user-resizable; the chosen width persists across
// sessions (alongside the open/closed state the parent already persists).
const WIDTH_STORAGE_KEY = "inkstave:agent-panel-width";
const MIN_WIDTH = 320;
const MAX_WIDTH = 800;
const DEFAULT_WIDTH = 448; // matches the previous fixed sm:max-w-md (28rem)

function clampWidth(px: number): number {
  return Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, px));
}

/** Persisted panel width with a drag handle on the panel's left edge. */
function usePanelWidth() {
  const [width, setWidth] = useState<number>(() => {
    try {
      const raw = localStorage.getItem(WIDTH_STORAGE_KEY);
      const parsed = raw ? Number.parseInt(raw, 10) : NaN;
      return Number.isFinite(parsed) ? clampWidth(parsed) : DEFAULT_WIDTH;
    } catch {
      return DEFAULT_WIDTH;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(WIDTH_STORAGE_KEY, String(width));
    } catch {
      /* ignore */
    }
  }, [width]);

  const dragging = useRef(false);

  const onPointerDown = useCallback(
    (e: React.PointerEvent) => {
      // The panel is docked right; dragging the left edge leftwards widens it.
      e.preventDefault();
      dragging.current = true;
      const move = (ev: PointerEvent) => {
        if (!dragging.current) return;
        setWidth(clampWidth(window.innerWidth - ev.clientX));
      };
      const up = () => {
        dragging.current = false;
        window.removeEventListener("pointermove", move);
        window.removeEventListener("pointerup", up);
      };
      window.addEventListener("pointermove", move);
      window.addEventListener("pointerup", up);
    },
    [setWidth],
  );

  const onKeyDown = useCallback((e: React.KeyboardEvent) => {
    // Keyboard-accessible resize (spec §5.4): arrows nudge the width.
    if (e.key === "ArrowLeft") {
      e.preventDefault();
      setWidth((w) => clampWidth(w + 16));
    } else if (e.key === "ArrowRight") {
      e.preventDefault();
      setWidth((w) => clampWidth(w - 16));
    }
  }, []);

  return { width, onPointerDown, onKeyDown };
}

function EmptyState({ onPick }: { onPick: (text: string) => void }) {
  const { t } = useTranslation("agent");
  const examples = [t("empty.example1"), t("empty.example2"), t("empty.example3")];
  return (
    <div className="flex-1 space-y-3 p-4 text-sm text-muted-foreground">
      <p>{t("empty.intro")}</p>
      <div className="flex flex-col gap-2">
        {examples.map((ex) => (
          <button
            key={ex}
            type="button"
            onClick={() => onPick(ex)}
            className="rounded-md border px-3 py-2 text-left text-xs hover:bg-muted"
          >
            {ex}
          </button>
        ))}
      </div>
    </div>
  );
}

export function AgentPanel({
  projectId,
  open,
  onOpenChange,
  onReviewProposal,
  documentBridge,
  onBeforeSend,
}: {
  projectId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onReviewProposal: (proposalId: string) => void;
  documentBridge?: DocumentBridge;
  /** Flush open collab docs before a run so the agent reads current text (spec 28/42). */
  onBeforeSend?: () => Promise<void>;
}) {
  const { t } = useTranslation("agent");
  const chat = useAgentChat(projectId, onBeforeSend);
  const [composerText, setComposerText] = useState("");
  const [reviewId, setReviewId] = useState<string | null>(null);
  const { width, onPointerDown, onKeyDown } = usePanelWidth();

  const handleReview = (proposalId: string) => {
    onReviewProposal(proposalId);
    if (documentBridge) setReviewId(proposalId);
  };

  const active = ACTIVE_PHASES.includes(chat.run.phase);
  const activeSession = chat.sessions.find((s) => s.id === chat.activeSessionId);
  const title = activeSession?.title ?? t("newChat");
  const noItems = chat.run.items.length === 0;
  const showLoading = chat.transcriptLoading && noItems;
  const isEmpty = noItems && !chat.transcriptLoading;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        aria-label={t("ariaLabel")}
        // Width is user-driven (drag handle below) and persisted; cap it on small
        // screens so it never overflows the viewport. The inline width overrides
        // the Sheet's default fixed width, making the panel resizable (spec §5.4).
        className="flex w-full max-w-[100vw] flex-col gap-0 p-0"
        style={{ width }}
      >
        {/* Drag-to-resize handle on the panel's left edge (spec §5.4). */}
        <div
          role="separator"
          aria-label={t("resizeHandle")}
          aria-orientation="vertical"
          tabIndex={0}
          onPointerDown={onPointerDown}
          onKeyDown={onKeyDown}
          className="absolute inset-y-0 left-0 z-10 w-1.5 cursor-col-resize bg-transparent hover:bg-border focus-visible:bg-border focus-visible:outline-none"
        />
        <SheetHeader className="space-y-0 border-b p-3">
          <div className="flex items-center justify-between gap-2 pr-6">
            <SheetTitle className="truncate text-base">{title}</SheetTitle>
            <div className="flex items-center gap-1">
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
                  <DropdownMenuItem onClick={() => void chat.newChat()}>
                    {t("newChat")}
                  </DropdownMenuItem>
                  {chat.sessions.length > 0 && <DropdownMenuSeparator />}
                  {chat.sessions.map((s) => (
                    <DropdownMenuItem key={s.id} onClick={() => void chat.selectSession(s.id)}>
                      {s.title ?? t("untitledChat")}
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>
          <SheetDescription className="sr-only">{t("description")}</SheetDescription>
        </SheetHeader>

        {showLoading ? (
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
        ) : isEmpty ? (
          <EmptyState onPick={setComposerText} />
        ) : (
          <AgentTranscript
            items={chat.run.items}
            loading={chat.transcriptLoading}
            onReviewProposal={handleReview}
          />
        )}

        {chat.run.error && <AgentErrorState error={chat.run.error} onRetry={chat.retry} />}

        <div className="border-t">
          {active && <RunControls onStop={() => void chat.stop()} />}
          <AgentComposer
            value={composerText}
            onChange={setComposerText}
            disabled={active}
            onSend={(text) => {
              void chat.send(text);
              setComposerText("");
            }}
          />
        </div>
      </SheetContent>

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
    </Sheet>
  );
}
