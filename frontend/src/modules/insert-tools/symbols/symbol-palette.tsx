import type { EditorView } from "@codemirror/view";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useMediaQuery } from "@/lib/use-media-query";

import { PackageHint } from "../package-hint";

import { insertSymbol } from "./insert-symbol";
import { recentEntries, readRecent } from "./recent-symbols";
import { SYMBOL_CATEGORIES, searchSymbols, type SymbolCategory, type SymbolEntry } from "./symbol-data";

type Filter = SymbolCategory | "all";

function SymbolGrid({
  label,
  entries,
  onChoose,
}: {
  label: string;
  entries: SymbolEntry[];
  onChoose: (entry: SymbolEntry) => void;
}) {
  const { t } = useTranslation("insert");
  return (
    <div
      role="group"
      aria-label={label}
      className="grid max-h-[40vh] grid-cols-6 gap-1 overflow-y-auto sm:grid-cols-8"
    >
      {entries.map((entry) => (
        <button
          key={entry.command}
          type="button"
          aria-label={entry.command}
          title={entry.package ? t("symbols.packageTip", { name: entry.package }) : undefined}
          onClick={() => onChoose(entry)}
          className="flex min-h-11 min-w-11 items-center justify-center rounded border font-serif text-heading hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {entry.unicode}
        </button>
      ))}
    </div>
  );
}

/** The palette's content, shared by the desktop dialog and the phone sheet. Choosing a symbol keeps it open. */
function SymbolPanel({ view, mainText }: { view: EditorView; mainText: string }) {
  const { t } = useTranslation("insert");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [recent, setRecent] = useState(readRecent);
  const [chosen, setChosen] = useState<SymbolEntry | null>(null);
  const shown = searchSymbols(query, filter);
  const onChoose = (entry: SymbolEntry) => {
    insertSymbol(view, entry);
    setRecent(readRecent());
    setChosen(entry);
  };
  const showRecent = query === "" && filter === "all" && recent.length > 0;
  const filters: Filter[] = ["all", ...SYMBOL_CATEGORIES];
  return (
    <div className="space-y-3">
      <Input
        type="search"
        autoFocus
        aria-label={t("symbols.search")}
        placeholder={t("symbols.placeholder")}
        value={query}
        onChange={(event) => setQuery(event.target.value)}
      />
      <div role="group" aria-label={t("symbols.tabs")} className="flex flex-wrap gap-1 text-small">
        {filters.map((id) => (
          <button
            key={id}
            type="button"
            aria-pressed={filter === id}
            onClick={() => setFilter(id)}
            className="min-h-8 rounded px-2 hover:bg-accent aria-pressed:bg-accent aria-pressed:font-medium"
          >
            {id === "all" ? t("symbols.all") : t(`symbols.categories.${id}`)}
          </button>
        ))}
      </div>
      {showRecent && (
        <SymbolGrid label={t("symbols.recent")} entries={recentEntries(recent)} onChoose={onChoose} />
      )}
      {shown.length > 0 ? (
        <SymbolGrid label={t("symbols.all")} entries={shown} onChoose={onChoose} />
      ) : (
        <p className="text-body text-muted-foreground">{t("symbols.empty", { query })}</p>
      )}
      <PackageHint pkg={chosen?.package} mainText={mainText} view={view} />
    </div>
  );
}

/** The symbol palette (spec 114 §5.2): a dialog on a wide screen, a bottom sheet on a phone. */
export function SymbolPalette({
  view,
  mainText,
  onClose,
}: {
  view: EditorView;
  mainText: string;
  onClose: () => void;
}) {
  const { t } = useTranslation("insert");
  const wide = useMediaQuery("(min-width: 768px)");
  const onOpenChange = (open: boolean) => {
    if (!open) onClose();
  };
  if (wide) {
    return (
      <Dialog open onOpenChange={onOpenChange}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>{t("symbols.title")}</DialogTitle>
            <DialogDescription>{t("symbols.description")}</DialogDescription>
          </DialogHeader>
          <SymbolPanel view={view} mainText={mainText} />
        </DialogContent>
      </Dialog>
    );
  }
  return (
    <Sheet open onOpenChange={onOpenChange}>
      <SheetContent side="bottom" className="max-h-[85dvh] overflow-y-auto">
        <SheetHeader>
          <SheetTitle>{t("symbols.title")}</SheetTitle>
          <SheetDescription>{t("symbols.description")}</SheetDescription>
        </SheetHeader>
        <SymbolPanel view={view} mainText={mainText} />
      </SheetContent>
    </Sheet>
  );
}
