import { Pin } from "lucide-react";
import { type KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import { Trans, useTranslation } from "react-i18next";

import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { type IndexStatus, type ResolvedItem, findCurrentEntry } from "@/modules/project-index";

export interface OutlinePanelProps {
  /** Sections and labels of the project; the labels are not shown here. */
  entries: ResolvedItem[];
  status: IndexStatus;
  openDocId: string | null;
  cursorLine: number;
  onOpen: (entry: ResolvedItem) => void;
  /** Present where the outline can be pinned beside the text (spec 111): the header carries the toggle. */
  pin?: { pinned: boolean; onToggle: () => void };
}

function nextFocus(key: string, focus: number, count: number): number | null {
  switch (key) {
    case "ArrowDown":
      return Math.min(focus + 1, count - 1);
    case "ArrowUp":
      return Math.max(focus - 1, 0);
    case "Home":
      return 0;
    case "End":
      return count - 1;
    default:
      return null;
  }
}

function fileName(path: string): string {
  return path.split("/").pop() ?? path;
}

function OutlineHeader({ pin }: { pin: OutlinePanelProps["pin"] }) {
  const { t } = useTranslation("editor");
  return (
    <div className="flex shrink-0 items-center justify-between gap-2 border-b border-control-edge px-3 py-1.5 text-small">
      <span className="font-medium">{t("outline.title")}</span>
      {pin && (
        <button
          type="button"
          aria-pressed={pin.pinned}
          aria-label={t("outline.pin")}
          title={t("outline.pin")}
          onClick={pin.onToggle}
          className={cn(
            "rounded p-1 hover:bg-accent hover:text-foreground",
            pin.pinned ? "text-foreground" : "text-muted-foreground",
          )}
        >
          <Pin className="size-4" aria-hidden />
        </button>
      )}
    </div>
  );
}

function OutlineEmpty({ loading }: { loading: boolean }) {
  const { t } = useTranslation("editor");
  if (loading) {
    return (
      <div className="space-y-2 px-3 py-2" aria-busy="true" aria-label={t("outline.loading")}>
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-4" style={{ width: `${80 - i * 15}%` }} />
        ))}
      </div>
    );
  }
  return (
    <p className="px-3 py-4 text-small text-muted-foreground">
      <Trans i18nKey="outline.empty" ns="editor" components={{ code: <code className="font-mono" /> }} />
    </p>
  );
}

interface RowProps {
  entry: ResolvedItem;
  current: boolean;
  focused: boolean;
  fromOtherFile: boolean;
  onActivate: () => void;
  rowRef: (element: HTMLLIElement | null) => void;
}

function OutlineRow({ entry, current, focused, fromOtherFile, onActivate, rowRef }: RowProps) {
  const level = entry.level ?? 0;
  const title = entry.title ?? "";
  return (
    <li
      role="treeitem"
      aria-level={level + 1}
      aria-current={current ? "location" : undefined}
      tabIndex={focused ? 0 : -1}
      ref={rowRef}
      onClick={onActivate}
      style={{ paddingInlineStart: `${0.5 + level * 0.75}rem` }}
      className={cn(
        "flex min-w-0 cursor-pointer items-baseline gap-2 border-l-2 py-1 pe-2 text-body hover:bg-accent",
        "focus-visible:outline focus-visible:outline-2 focus-visible:outline-focus",
        current ? "border-foreground bg-accent font-medium" : "border-transparent",
      )}
    >
      <span className="min-w-0 truncate" title={title}>
        {title}
      </span>
      {fromOtherFile && (
        <span className="shrink-0 truncate text-small text-muted-foreground">{fileName(entry.path)}</span>
      )}
    </li>
  );
}

/** The document outline (spec 111): the sections of the project, the current one marked, a tree for the keyboard. */
export function OutlinePanel({ entries, status, openDocId, cursorLine, onOpen, pin }: OutlinePanelProps) {
  const { t } = useTranslation("editor");
  const sections = useMemo(() => entries.filter((entry) => entry.kind === "section"), [entries]);
  const current = findCurrentEntry(sections, openDocId, cursorLine);
  const [focus, setFocus] = useState(0);
  const rows = useRef<(HTMLLIElement | null)[]>([]);

  // The row the cursor is in stays in view and becomes the one the arrow keys start from.
  useEffect(() => {
    if (current < 0) return;
    setFocus(current);
    rows.current[current]?.scrollIntoView({ block: "nearest" });
  }, [current]);

  const onKeyDown = (event: KeyboardEvent<HTMLUListElement>) => {
    const entry = sections[focus];
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      if (entry) onOpen(entry);
      return;
    }
    const next = nextFocus(event.key, focus, sections.length);
    if (next === null) return;
    event.preventDefault();
    setFocus(next);
    rows.current[next]?.focus();
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <OutlineHeader pin={pin} />
      {status === "limited" && (
        <p role="status" className="shrink-0 border-b px-3 py-2 text-small text-muted-foreground">
          {t("outline.limited")}
        </p>
      )}
      <div className="min-h-0 flex-1 overflow-auto py-1">
        {sections.length === 0 ? (
          <OutlineEmpty loading={status === "loading"} />
        ) : (
          <ul role="tree" aria-label={t("outline.tree")} onKeyDown={onKeyDown}>
            {sections.map((entry, index) => (
              <OutlineRow
                key={`${entry.docId}:${entry.line}`}
                entry={entry}
                current={index === current}
                focused={index === focus}
                fromOtherFile={entry.docId !== openDocId}
                onActivate={() => {
                  setFocus(index);
                  onOpen(entry);
                }}
                rowRef={(element) => {
                  rows.current[index] = element;
                }}
              />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
