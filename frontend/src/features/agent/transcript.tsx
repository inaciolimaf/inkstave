/** Transcript rendering: message bubbles, tool rows, diff cards (spec 46). */
import { Check, ChevronDown, ChevronRight, FileDiff, Loader2, X } from "lucide-react";
import { type ReactNode, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

import { Markdown } from "./Markdown";
import type { TranscriptItem } from "./types";

const TOOL_LABELS: Record<string, string> = {
  search_project: "Searched the project",
  read_file: "Read a file",
  list_tree: "Listed the file tree",
  locate_section: "Located a section",
  propose_edit: "Proposed an edit",
};

/** Render text as plain, escaped React children (no HTML execution), with ``` code blocks. */
function renderText(text: string): ReactNode {
  return text.split(/(```[\s\S]*?```)/g).map((part, i) => {
    if (part.startsWith("```") && part.endsWith("```") && part.length >= 6) {
      const code = part.slice(3, -3).replace(/^[a-zA-Z0-9]*\n/, "");
      return (
        <pre
          key={i}
          className="my-1 overflow-x-auto rounded bg-background/60 p-2 font-mono text-xs"
        >
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
  const isUser = item.role === "user";
  return (
    <div
      data-role={item.role}
      data-status={item.status}
      className={cn(
        "max-w-[85%] rounded-lg px-3 py-2 text-sm",
        isUser ? "ml-auto bg-primary text-primary-foreground" : "mr-auto bg-muted",
      )}
    >
      {isUser ? renderText(item.text) : <Markdown>{item.text}</Markdown>}
      {item.status === "streaming" && (
        <span className="ml-0.5 inline-block animate-pulse" aria-hidden="true">
          ▋
        </span>
      )}
      {item.status === "cancelled" && (
        <span className="mt-1 block text-xs italic text-muted-foreground">Run cancelled</span>
      )}
    </div>
  );
}

function ToolActivityRow({ item }: { item: Extract<TranscriptItem, { kind: "tool" }> }) {
  const [open, setOpen] = useState(false);
  const label = TOOL_LABELS[item.name] ?? item.name;
  const icon =
    item.status === "running" ? (
      <Loader2 className="size-3.5 animate-spin text-muted-foreground" aria-hidden="true" />
    ) : item.status === "ok" ? (
      <Check className="size-3.5 text-green-600" aria-hidden="true" />
    ) : (
      <X className="size-3.5 text-destructive" aria-hidden="true" />
    );
  return (
    <div className="mr-auto max-w-[85%] rounded-md border text-xs" data-status={item.status}>
      <button
        type="button"
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-2 py-1.5 text-left"
        onClick={() => setOpen((o) => !o)}
      >
        {icon}
        <span className="flex-1 truncate">{label}</span>
        {open ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
      </button>
      {open && (
        <pre className="overflow-x-auto border-t bg-muted/50 p-2 font-mono text-[11px]">
          {JSON.stringify({ args: item.args, result: item.result }, null, 2)}
        </pre>
      )}
    </div>
  );
}

function DiffProposalCard({
  item,
  onReviewProposal,
}: {
  item: Extract<TranscriptItem, { kind: "diff-proposal" }>;
  onReviewProposal: (proposalId: string) => void;
}) {
  const hunks = item.files.reduce((n, f) => n + f.hunkCount, 0);
  return (
    <Card className="mr-auto max-w-[85%] space-y-2 p-3">
      <div className="flex items-center gap-2 text-sm font-medium">
        <FileDiff className="size-4 text-primary" aria-hidden="true" />
        Proposed changes
      </div>
      <ul className="text-xs text-muted-foreground">
        {item.files.map((f) => (
          <li key={f.path}>
            {f.path} · {f.hunkCount} hunk{f.hunkCount === 1 ? "" : "s"}
          </li>
        ))}
      </ul>
      <Button size="sm" onClick={() => onReviewProposal(item.proposalId)}>
        Review changes{hunks ? ` (${hunks})` : ""}
      </Button>
    </Card>
  );
}

export function AgentTranscript({
  items,
  loading,
  onReviewProposal,
}: {
  items: TranscriptItem[];
  loading: boolean;
  onReviewProposal: (proposalId: string) => void;
}) {
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
        aria-label="Conversation"
        className="flex h-full flex-col gap-2 overflow-auto p-3"
      >
        {items.map((item) => {
          if (item.kind === "message") return <MessageBubble key={item.id} item={item} />;
          if (item.kind === "tool") return <ToolActivityRow key={item.id} item={item} />;
          if (item.kind === "diff-proposal") {
            return (
              <DiffProposalCard key={item.id} item={item} onReviewProposal={onReviewProposal} />
            );
          }
          return (
            <div key={item.id} className="text-xs text-destructive" role="alert">
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
          Jump to latest
        </Button>
      )}
    </div>
  );
}
