import type { EditorView } from "@codemirror/view";
import { Plus, Sigma, Sheet, Table2 } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useShortcuts } from "@/lib/shortcuts";

import { EquationDialog } from "./equation/equation-dialog";
import { SymbolPalette } from "./symbols/symbol-palette";
import { TableBuilder } from "./table/table-builder";

type Tool = "symbol" | "table" | "equation";

/**
 * The Insert button of the editor bar (spec 114 §5.1). It belongs to the open document: every tool writes to
 * that view, and a viewer gets the button disabled. Only the open tool is mounted, so each one starts fresh.
 */
export function InsertMenu({
  view,
  readOnly,
  mainText,
}: {
  view: EditorView | null;
  readOnly: boolean;
  /** The main document's text, for the packages it loads; the open text stands in until it is known. */
  mainText: string | undefined;
}) {
  const { t } = useTranslation("insert");
  const [tool, setTool] = useState<Tool | null>(null);
  const disabled = readOnly || view === null;
  useShortcuts(
    {
      "mod+shift+y": () => setTool("symbol"),
      "mod+shift+e": () => setTool("equation"),
    },
    !disabled,
  );
  const text = mainText ?? view?.state.doc.toString() ?? "";
  const close = () => setTool(null);
  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            size="sm"
            variant="ghost"
            disabled={disabled}
            aria-label={t("menu.trigger")}
            className="h-8 gap-1 px-2"
          >
            <Plus aria-hidden="true" className="size-4" />
            <span className="hidden lg:inline">{t("menu.trigger")}</span>
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onSelect={() => setTool("symbol")}>
            <Sigma aria-hidden="true" className="size-4" />
            {t("menu.symbol")}
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={() => setTool("table")}>
            <Table2 aria-hidden="true" className="size-4" />
            {t("menu.table")}
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={() => setTool("equation")}>
            <Sheet aria-hidden="true" className="size-4" />
            {t("menu.equation")}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      {view && tool === "symbol" && <SymbolPalette view={view} mainText={text} onClose={close} />}
      {view && tool === "table" && <TableBuilder view={view} mainText={text} onClose={close} />}
      {view && tool === "equation" && <EquationDialog view={view} onClose={close} />}
    </>
  );
}
