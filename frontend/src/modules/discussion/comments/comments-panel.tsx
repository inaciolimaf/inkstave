/**
 * The comments panel (spec 118): a column beside the text on a wide screen, a sheet on a phone. It lists
 * the threads with filters (Open, Resolved, All) and a scope (this file, all files), and holds the box for
 * a new comment on the selected text.
 */
import { X } from "lucide-react";
import { useEffect, useMemo, useReducer, useState } from "react";
import { useTranslation } from "react-i18next";
import type * as Y from "yjs";

import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";

import { SuggestionsTab, type SuggestionsTabProps } from "../suggestions-tab";
import { type ResolvedRange, resolveAnchor } from "./anchors";
import type { CommentThread } from "./api";
import { CommentComposer } from "./composer";
import { type MentionCandidate } from "./mentions";
import { type ThreadScope, type ThreadStatusFilter, orderThreads } from "./order";
import { ThreadView } from "./thread";

export interface CommentDraft {
  quote: string;
}

export interface CommentsPanelProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** A wide screen shows a column; a phone shows a sheet. */
  wide: boolean;
  projectId: string;
  threads: CommentThread[];
  /** The open document's text, to place its threads; null without a collaborative editor. */
  ytext: Y.Text | null;
  currentDocumentId: string | null;
  fileName: (documentId: string) => string;
  members: MentionCandidate[];
  meId: string | null;
  selectedId: string | null;
  onSelect: (thread: CommentThread) => void;
  draft: CommentDraft | null;
  creating: boolean;
  onCreate: (body: string, mentions: string[]) => void;
  onDraftCancel: () => void;
  /** The Suggestions tab (spec 119); null where the document has no collaborative text. */
  suggestions?: SuggestionsTabProps | null;
}

/** The two tabs of the review column (spec 119). */
export type ReviewTab = "comments" | "suggestions";

/** The current range of each thread of the open document, kept in step with the text. */
function useThreadRanges(
  ytext: Y.Text | null,
  threads: CommentThread[],
  documentId: string | null,
): Map<string, ResolvedRange | null> {
  const [revision, bump] = useReducer((n: number) => n + 1, 0);
  useEffect(() => {
    if (!ytext) return undefined;
    ytext.observe(bump);
    return () => ytext.unobserve(bump);
  }, [ytext]);
  return useMemo(() => {
    const ranges = new Map<string, ResolvedRange | null>();
    if (!ytext) return ranges;
    for (const thread of threads) {
      if (thread.document_id !== documentId) continue;
      ranges.set(thread.id, resolveAnchor(ytext, thread.anchor_start, thread.anchor_end));
    }
    return ranges;
    // `revision` is the signal that the text changed; the ranges are read from `ytext` below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ytext, threads, documentId, revision]);
}

function ReviewTabs({ tab, onChange }: { tab: ReviewTab; onChange: (tab: ReviewTab) => void }) {
  const { t } = useTranslation("discussion");
  const tabs: ReviewTab[] = ["comments", "suggestions"];
  return (
    <div role="group" aria-label={t("comments.tabs.label")} className="flex gap-1 border-b p-2 text-small">
      {tabs.map((value) => (
        <button
          key={value}
          type="button"
          aria-pressed={tab === value}
          onClick={() => onChange(value)}
          className={cn(
            "rounded px-2 py-1",
            tab === value ? "bg-accent font-medium" : "text-muted-foreground hover:text-foreground",
          )}
        >
          {t(`comments.tabs.${value}`)}
        </button>
      ))}
    </div>
  );
}

/** The panel's content: the comment threads, or the Suggestions tab where the document has suggestions. */
function PanelContent(props: CommentsPanelProps & { ranges: Map<string, ResolvedRange | null> }) {
  const [tab, setTab] = useState<ReviewTab>("comments");
  if (!props.suggestions) return <PanelBody {...props} />;
  return (
    <div className="flex h-full min-h-0 flex-col">
      <ReviewTabs tab={tab} onChange={setTab} />
      {tab === "suggestions" ? (
        <div className="min-h-0 flex-1 overflow-auto p-3">
          <SuggestionsTab {...props.suggestions} />
        </div>
      ) : (
        <PanelBody {...props} />
      )}
    </div>
  );
}

const FILTERS: ThreadStatusFilter[] = ["open", "resolved", "all"];
const SCOPES: ThreadScope[] = ["file", "all"];

function PanelBody(props: CommentsPanelProps & { ranges: Map<string, ResolvedRange | null> }) {
  const { t } = useTranslation("discussion");
  const [filter, setFilter] = useState<ThreadStatusFilter>("open");
  const [scope, setScope] = useState<ThreadScope>("file");
  const rows = orderThreads(props.threads, {
    currentDocumentId: props.currentDocumentId,
    ranges: props.ranges,
    fileName: props.fileName,
    filter,
    scope,
  });

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="space-y-2 border-b p-3">
        <div role="group" aria-label={t("comments.filter.label")} className="flex flex-wrap gap-1">
          {FILTERS.map((value) => (
            <Button
              key={value}
              size="sm"
              variant={filter === value ? "default" : "ghost"}
              aria-pressed={filter === value}
              onClick={() => setFilter(value)}
            >
              {t(`comments.filter.${value}`)}
            </Button>
          ))}
        </div>
        <div role="group" aria-label={t("comments.scope.label")} className="flex gap-1 text-small">
          {SCOPES.map((value) => (
            <button
              key={value}
              type="button"
              aria-pressed={scope === value}
              onClick={() => setScope(value)}
              className={cn(
                "rounded px-2 py-1",
                scope === value ? "bg-accent font-medium" : "text-muted-foreground hover:text-foreground",
              )}
            >
              {t(`comments.scope.${value}`)}
            </button>
          ))}
        </div>
      </div>
      <div className="min-h-0 flex-1 space-y-3 overflow-auto p-3">
        {props.draft && (
          <CommentComposer
            quote={props.draft.quote}
            members={props.members}
            pending={props.creating}
            onSubmit={props.onCreate}
            onCancel={props.onDraftCancel}
          />
        )}
        {rows.length === 0 && !props.draft && (
          <p className="py-6 text-center text-body text-muted-foreground">{t("comments.empty")}</p>
        )}
        {rows.map(({ thread, current, range }) => (
          <div key={thread.id} className="space-y-1">
            {scope === "all" && (
              <p className="text-small font-medium text-muted-foreground">
                {props.fileName(thread.document_id)}
              </p>
            )}
            <ThreadView
              projectId={props.projectId}
              thread={thread}
              detached={current && range === null}
              members={props.members}
              meId={props.meId}
              selected={thread.id === props.selectedId}
              onOpen={() => props.onSelect(thread)}
            />
          </div>
        ))}
      </div>
    </div>
  );
}

export function CommentsPanel(props: CommentsPanelProps) {
  const { t } = useTranslation("discussion");
  const ranges = useThreadRanges(props.ytext, props.threads, props.currentDocumentId);
  if (!props.open) return null;
  if (!props.wide) {
    return (
      <Sheet open={props.open} onOpenChange={props.onOpenChange}>
        <SheetContent side="right" className="flex w-full max-w-md flex-col p-0 sm:max-w-md">
          <SheetHeader className="border-b p-3 text-left">
            <SheetTitle>{t("comments.title")}</SheetTitle>
            <SheetDescription className="sr-only">{t("comments.description")}</SheetDescription>
          </SheetHeader>
          <PanelContent {...props} ranges={ranges} />
        </SheetContent>
      </Sheet>
    );
  }
  return (
    <aside
      aria-label={t("comments.title")}
      className="flex h-full w-80 shrink-0 flex-col border-l bg-background"
    >
      <div className="flex items-center justify-between border-b px-3 py-2">
        <h2 className="text-body font-medium">{t("comments.title")}</h2>
        <Button
          size="icon"
          variant="ghost"
          onClick={() => props.onOpenChange(false)}
          aria-label={t("comments.close")}
        >
          <X aria-hidden="true" className="size-4" />
        </Button>
      </div>
      <PanelContent {...props} ranges={ranges} />
    </aside>
  );
}
