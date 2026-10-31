import { Sparkles } from "lucide-react";
import { useTranslation } from "react-i18next";

import { placeAbove, type EditorSelection } from "./use-editor-selection";

/**
 * Offers the agent where the text was selected. On a phone the system's own selection menu sits above
 * the text, so the button waits in a fixed spot over the tabs (spec 107).
 */
export function AskAgentButton({
  selection,
  floating,
  onAsk,
}: {
  selection: EditorSelection;
  floating: boolean;
  onAsk: () => void;
}) {
  const { t } = useTranslation("editor");
  if (floating && !selection.anchor) return null;
  const style = floating && selection.anchor ? placeAbove(selection.anchor, window.innerWidth) : undefined;
  return (
    <button
      type="button"
      style={style}
      // Pressing must not take the focus, or the editor would drop the selection first.
      onMouseDown={(e) => e.preventDefault()}
      onClick={onAsk}
      className={
        (floating ? "fixed " : "fixed bottom-24 left-1/2 -translate-x-1/2 ") +
        "z-30 inline-flex min-h-9 items-center gap-1.5 rounded border border-control-edge bg-popover px-3 text-small font-medium shadow-md hover:bg-accent"
      }
    >
      <Sparkles aria-hidden="true" className="size-4" />
      {t("selection.ask")}
    </button>
  );
}
