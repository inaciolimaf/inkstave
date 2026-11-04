import { MessageSquareQuote } from "lucide-react";
import { useTranslation } from "react-i18next";

import { placeAbove, type EditorSelection } from "./use-editor-selection";

/**
 * Offers a comment on the selected text, beside "Ask the agent" (spec 118). It sits to the right of the
 * agent button's spot; on a phone it waits in a fixed place over the tabs, as the agent button does.
 */
export function CommentSelectionButton({
  selection,
  floating,
  onComment,
}: {
  selection: EditorSelection;
  floating: boolean;
  onComment: () => void;
}) {
  const { t } = useTranslation("discussion");
  if (floating && !selection.anchor) return null;
  const placed = floating && selection.anchor ? placeAbove(selection.anchor, window.innerWidth) : undefined;
  const style = placed ? { left: placed.left + 190, top: placed.top } : undefined;
  return (
    <button
      type="button"
      style={style}
      // Pressing must not take the focus, or the editor would drop the selection first.
      onMouseDown={(e) => e.preventDefault()}
      onClick={onComment}
      className={
        (floating ? "fixed " : "fixed bottom-24 left-4 ") +
        "z-30 inline-flex min-h-9 items-center gap-1.5 rounded border border-control-edge bg-popover px-3 text-small font-medium shadow-md hover:bg-accent"
      }
    >
      <MessageSquareQuote aria-hidden="true" className="size-4" />
      {t("comments.selection.comment")}
    </button>
  );
}
