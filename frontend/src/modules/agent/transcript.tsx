/**
 * Transcript rendering (spec 46). Everything the agent did is the hand (spec 106): a stroke in the
 * margin of the text, while the writer's own messages open a ruled entry.
 */
import { Check, ChevronDown, ChevronRight, FileDiff, Loader2, X } from "lucide-react";
import { Fragment, type ReactNode, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

import { Markdown } from "./Markdown";
import type { TranscriptItem } from "./types";

const HAND = "min-w-0 border-l-2 border-primary pl-3";

const TOOL_LABEL_KEYS: Record<string, string> = {
  search_project: "transcript.tools.search_project",
  read_file: "transcript.tools.read_file",
  list_tree: "transcript.tools.list_tree",
  locate_section: "transcript.tools.locate_section",
  propose_edit: "transcript.tools.propose_edit",
  view_image: "transcript.tools.view_image",
  propose_create: "transcript.tools.propose_create",
  propose_delete: "transcript.tools.propose_delete",
  propose_move: "transcript.tools.propose_move",
};

/** Render text as plain, escaped React children (no HTML execution), with ``` code blocks. */
function renderText(text: string): ReactNode {
  return text.split(/(```[\s\S]*?```)/g).map((part, i) => {
    if (part.startsWith("```") && part.endsWith("```") && part.length >= 6) {
      const code = part.slice(3, -3).replace(/^[a-zA-Z0-9]*\n/, "");
      return (
        <pre key={i} className="my-1 overflow-x-auto border-y py-1.5 font-mono text-small">
          <code>{code}</code>
        </pre>
      );
    }
    return (
      <span key={i} className="whitespace-pre-wrap">
        {part}
      </span>
    );
  });
}

function MessageBubble({ item }: { item: Extract<TranscriptItem, { kind: "message" }> }) {
  const { t } = useTranslation("agent");
  const isUser = item.role === "user";
  return (
    <div
      data-role={item.role}
      data-status={item.status}
      className={cn(
        "min-w-0 text-body",
        isUser ? "border-t pt-3 font-medium first:border-t-0 first:pt-0" : HAND,
      )}
    >
      {isUser ? renderText(item.text) : <Markdown>{item.text}</Markdown>}
      {item.status === "streaming" && (
        <span className="ml-0.5 inline-block animate-pulse" aria-hidden="true">
          ▋
        </span>
      )}
      {item.status === "cancelled" && (
        <span className="mt-1 block text-small italic text-muted-foreground">
          {t("transcript.runCancelled")}
        </span>
      )}
    </div>
  );
}

type ToolItem = Extract<TranscriptItem, { kind: "tool" }>;

function StatusIcon({ status }: { status: ToolItem["status"] }) {
  if (status === "running") {
    return <Loader2 className="size-3.5 animate-spin text-muted-foreground" aria-hidden="true" />;
  }
  if (status === "ok") return <Check className="size-3.5 text-success-text" aria-hidden="true" />;
  return <X className="size-3.5 text-error-text" aria-hidden="true" />;
}

/** What a step touched, for a person: the file or the search, never the raw call. */
function toolTarget(args: unknown): string | null {
  if (typeof args !== "object" || args === null) return null;
  const { path, query, name } = args as { path?: unknown; query?: unknown; name?: unknown };
  const target = path ?? query ?? name;
  return typeof target === "string" ? target : null;
}

/** A run's tool calls fold into one line (spec 107): the agent's steps are not the conversation. */
function ToolActivity({ items }: { items: ToolItem[] }) {
  const { t } = useTranslation("agent");
  const [open, setOpen] = useState(false);
  const label = (item: ToolItem) => {
    const key = TOOL_LABEL_KEYS[item.name];
    return key ? t(key) : item.name;
  };
  const running = items.find((item) => item.status === "running");
  const failed = items.some((item) => item.status === "error");
  const summary = running ? label(running) : t("transcript.steps", { count: items.length });
  const status = running ? "running" : failed ? "error" : "ok";
  return (
    <div className={cn(HAND, "text-small text-muted-foreground")} data-status={status}>
      <button
        type="button"
        aria-expanded={open}
        className="flex w-full items-center gap-2 py-0.5 text-left hover:text-foreground"
        onClick={() => setOpen((o) => !o)}
      >
        <StatusIcon status={status} />
        <span className="flex-1 truncate">{summary}</span>
        {open ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
      </button>
      {open && (
        <ul className="space-y-0.5 pb-1 pl-5">
          {items.map((item) => (
            <li key={item.id} className="flex min-w-0 items-center gap-2">
              <StatusIcon status={item.status} />
              <span className="min-w-0 truncate">
                {label(item)}
                {toolTarget(item.args) && <span className="font-mono"> {toolTarget(item.args)}</span>}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Groups neighbouring tool calls, so a long run reads as a few lines. */
function foldTools(items: TranscriptItem[]): (Exclude<TranscriptItem, ToolItem> | ToolItem[])[] {
  const folded: (Exclude<TranscriptItem, ToolItem> | ToolItem[])[] = [];
  for (const item of items) {
    const last = folded[folded.length - 1];
    if (item.kind !== "tool") folded.push(item);
    else if (Array.isArray(last)) last.push(item);
    else folded.push([item]);
  }
  return folded;
}

function DiffProposalCard({
  item,
  onReviewProposal,
}: {
  item: Extract<TranscriptItem, { kind: "diff-proposal" }>;
  onReviewProposal: (proposalId: string) => void;
}) {
  const { t } = useTranslation("agent");
  const hunks = item.files.reduce((n, f) => n + f.hunkCount, 0);
  return (
    <div className={cn(HAND, "space-y-2")}>
      <div className="flex items-center gap-2 text-body font-medium">
        <FileDiff className="size-4 text-primary" aria-hidden="true" />
        {t("transcript.proposedChanges")}
      </div>
      <ul className="text-small text-muted-foreground">
        {item.files.map((f) => (
          <li key={f.path}>{t("transcript.hunkLine", { path: f.path, count: f.hunkCount })}</li>
        ))}
      </ul>
      <Button size="sm" variant="outline" onClick={() => onReviewProposal(item.proposalId)}>
        {hunks ? t("transcript.reviewChangesCount", { count: hunks }) : t("transcript.reviewChanges")}
      </Button>
    </div>
  );
}

export function AgentTranscript({
  items,
  loading,
  onReviewProposal,
  renderFileOp,
}: {
  items: TranscriptItem[];
  loading: boolean;
  onReviewProposal: (proposalId: string) => void;
  renderFileOp?: (item: Extract<TranscriptItem, { kind: "file-op" }>) => ReactNode;
}) {
  const { t } = useTranslation("agent");
  const ref = useRef<HTMLDivElement>(null);
  const [pinned, setPinned] = useState(true);

  useEffect(() => {
    if (pinned && ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [items, pinned]);

  const onScroll = () => {
    const el = ref.current;
    if (!el) return;
    setPinned(el.scrollHeight - el.scrollTop - el.clientHeight < 48);
  };

  // Announce only completed assistant messages / errors to screen readers — never the
  // per-token stream (a live region over the whole log re-reads the growing message).
  let announce = "";
  for (let i = items.length - 1; i >= 0; i--) {
    const it = items[i];
    if (it.kind === "message" && it.role === "assistant" && it.status === "complete") {
      announce = it.text;
      break;
    }
    if (it.kind === "error") {
      announce = it.message;
      break;
    }
  }

  if (loading) {
    return (
      <div className="flex-1 space-y-2 p-3" aria-busy="true">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-10" />
        ))}
      </div>
    );
  }

  return (
    <div className="relative min-h-0 flex-1">
      <div
        ref={ref}
        onScroll={onScroll}
        role="log"
        aria-label={t("transcript.conversation")}
        className="flex h-full flex-col gap-3 overflow-auto p-3"
      >
        {foldTools(items).map((item) => {
          if (Array.isArray(item)) return <ToolActivity key={item[0]!.id} items={item} />;
          if (item.kind === "message") return <MessageBubble key={item.id} item={item} />;
          if (item.kind === "diff-proposal") {
            return <DiffProposalCard key={item.id} item={item} onReviewProposal={onReviewProposal} />;
          }
          if (item.kind === "file-op") return <Fragment key={item.id}>{renderFileOp?.(item)}</Fragment>;
          return (
            <div key={item.id} className="text-small text-error-text" role="alert">
              {item.message}
            </div>
          );
        })}
      </div>
      <div className="sr-only" role="status" aria-live="polite">
        {announce}
      </div>
      {!pinned && (
        <Button
          size="sm"
          variant="secondary"
          className="absolute bottom-2 left-1/2 -translate-x-1/2"
          onClick={() => setPinned(true)}
        >
          {t("transcript.jumpToLatest")}
        </Button>
      )}
    </div>
  );
}
