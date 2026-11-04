/** The fields of the search panel (spec 122): the query, its three options, and the replacement. */
import { CaseSensitive, Regex, WholeWord } from "lucide-react";
import { type ComponentType, type RefObject, type SVGProps } from "react";
import { useTranslation } from "react-i18next";

import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

import type { SearchOptions } from "./matcher";
import type { ProjectSearchState } from "./use-project-search";

const TOGGLES: { key: keyof SearchOptions; label: string; Icon: ComponentType<SVGProps<SVGSVGElement>> }[] = [
  { key: "caseSensitive", label: "caseSensitive", Icon: CaseSensitive },
  { key: "wholeWord", label: "wholeWord", Icon: WholeWord },
  { key: "regex", label: "regex", Icon: Regex },
];

function OptionToggles({ state }: { state: ProjectSearchState }) {
  const { t } = useTranslation("search");
  return (
    <div role="group" aria-label={t("options")} className="flex shrink-0 gap-0.5">
      {TOGGLES.map(({ key, label, Icon }) => {
        const on = state.options[key];
        return (
          <button
            key={key}
            type="button"
            aria-pressed={on}
            aria-label={t(label)}
            title={t(label)}
            onClick={() => state.setOptions({ ...state.options, [key]: !on })}
            className={cn(
              "rounded p-1 hover:bg-accent hover:text-foreground",
              on ? "bg-accent text-foreground" : "text-muted-foreground",
            )}
          >
            <Icon className="size-4" aria-hidden />
          </button>
        );
      })}
    </div>
  );
}

export function SearchControls({
  state,
  inputRef,
}: {
  state: ProjectSearchState;
  inputRef: RefObject<HTMLInputElement | null>;
}) {
  const { t } = useTranslation("search");
  return (
    <div className="space-y-1.5 border-b border-control-edge px-2 py-2">
      <div className="flex items-center gap-1">
        <Input
          ref={inputRef}
          type="search"
          value={state.query}
          onChange={(e) => state.setQuery(e.target.value)}
          aria-label={t("query")}
          placeholder={t("queryPlaceholder")}
          title={`${t("query")} (${t("shortcut")})`}
          spellCheck={false}
          aria-invalid={state.error !== null}
          className="h-8 min-w-0 flex-1 font-mono text-small"
        />
        <OptionToggles state={state} />
      </div>
      {state.canReplace && (
        <Input
          type="text"
          value={state.replacement}
          onChange={(e) => state.setReplacement(e.target.value)}
          aria-label={t("replacement")}
          placeholder={t("replacementPlaceholder")}
          spellCheck={false}
          className="h-8 font-mono text-small"
        />
      )}
    </div>
  );
}
