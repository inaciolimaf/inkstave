/** A message box with an `@` member menu (spec 118). Picks are reported; the server gets only the ids. */
import { type KeyboardEvent, useLayoutEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

import { type MentionCandidate, insertMention, matchingMembers, mentionQuery } from "./mentions";

export interface MentionTextareaProps {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  /** Called with each member picked from the menu. */
  onPick: (member: MentionCandidate) => void;
  members: MentionCandidate[];
  placeholder?: string;
  rows?: number;
  className?: string;
  /** Ctrl/Cmd+Enter, when the box is a message to send. */
  onSubmit?: () => void;
}

/** The menu of members for the `@` word being typed. Pressing an option takes it without moving focus. */
function MentionMenu({
  listId,
  options,
  active,
  onPick,
}: {
  listId: string;
  options: MentionCandidate[];
  active: number;
  onPick: (member: MentionCandidate) => void;
}) {
  const { t } = useTranslation("discussion");
  return (
    <ul
      id={listId}
      role="listbox"
      aria-label={t("comments.mentions.label")}
      className="absolute bottom-full left-0 z-20 mb-1 max-h-48 w-64 max-w-full overflow-auto rounded-md border bg-popover p-1 shadow-md"
    >
      {options.map((member, index) => (
        <li
          key={member.id}
          id={`${listId}-${index}`}
          role="option"
          aria-selected={index === active}
          className={cn(
            "cursor-pointer rounded px-2 py-1 text-body",
            index === active && "bg-accent text-accent-foreground",
          )}
          onMouseDown={(event) => {
            event.preventDefault();
            onPick(member);
          }}
        >
          {member.name}
        </li>
      ))}
    </ul>
  );
}

/** The key handling while the menu is open: arrows move, Enter or Tab picks, Escape closes. */
function menuKey(
  key: string,
  count: number,
  active: number,
): { kind: "move"; active: number } | { kind: "pick"; index: number } | { kind: "close" } | null {
  if (key === "ArrowDown" || key === "ArrowUp") {
    const step = key === "ArrowDown" ? 1 : -1;
    return { kind: "move", active: (active + step + count) % count };
  }
  if (key === "Enter" || key === "Tab") return { kind: "pick", index: active };
  if (key === "Escape") return { kind: "close" };
  return null;
}

export function MentionTextarea({
  id,
  label,
  value,
  onChange,
  onPick,
  members,
  placeholder,
  rows = 2,
  className,
  onSubmit,
}: MentionTextareaProps) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const pendingCaret = useRef<number | null>(null);
  const [caret, setCaret] = useState(0);
  const [active, setActive] = useState(0);
  const [dismissed, setDismissed] = useState(false);

  const query = dismissed ? null : mentionQuery(value, caret);
  const options = query ? matchingMembers(members, query.query).slice(0, 6) : [];
  const open = options.length > 0;
  const listId = `${id}-mentions`;

  useLayoutEffect(() => {
    if (pendingCaret.current === null || !ref.current) return;
    ref.current.setSelectionRange(pendingCaret.current, pendingCaret.current);
    pendingCaret.current = null;
  });

  const pick = (member: MentionCandidate) => {
    if (!query) return;
    const next = insertMention(value, caret, query.start, member.name);
    pendingCaret.current = next.caret;
    setCaret(next.caret);
    setActive(0);
    onChange(next.value);
    onPick(member);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    const action = open ? menuKey(event.key, options.length, active) : null;
    if (action) {
      event.preventDefault();
      if (action.kind === "move") setActive(action.active);
      if (action.kind === "close") setDismissed(true);
      const chosen = action.kind === "pick" ? options[action.index] : undefined;
      if (chosen) pick(chosen);
      return;
    }
    if (onSubmit && event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      onSubmit();
    }
  };

  return (
    <div className="relative">
      <Textarea
        id={id}
        ref={ref}
        rows={rows}
        value={value}
        placeholder={placeholder}
        aria-label={label}
        aria-autocomplete="list"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        aria-activedescendant={open ? `${listId}-${active}` : undefined}
        role="combobox"
        className={cn("text-body", className)}
        onChange={(event) => {
          setDismissed(false);
          setCaret(event.target.selectionStart);
          onChange(event.target.value);
        }}
        onSelect={(event) => setCaret(event.currentTarget.selectionStart)}
        onKeyDown={onKeyDown}
      />
      {open && <MentionMenu listId={listId} options={options} active={active} onPick={pick} />}
    </div>
  );
}
