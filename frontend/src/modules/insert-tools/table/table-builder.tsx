import type { EditorView } from "@codemirror/view";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

import { insertBlock } from "../insert-text";
import { PackageHint } from "../package-hint";

import { TableGrid } from "./table-grid";
import { TableOptions } from "./table-options";
import { emptyTable, type TableDraft } from "./table-model";
import { tableToLatex } from "./to-latex";

/**
 * The table builder (spec 114 §5.3). It only creates a table: the code goes in at the cursor, and an existing
 * `tabular` is never read back. Mounted only while open, so every opening starts from an empty grid.
 */
export function TableBuilder({
  view,
  mainText,
  onClose,
}: {
  view: EditorView;
  mainText: string;
  onClose: () => void;
}) {
  const { t } = useTranslation("insert");
  const [draft, setDraft] = useState<TableDraft>(() => emptyTable());
  const update = (change: (current: TableDraft) => TableDraft) => setDraft((current) => change(current));
  const code = tableToLatex(draft);
  const insert = () => {
    insertBlock(view, code);
    onClose();
  };
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90dvh] max-w-3xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t("table.title")}</DialogTitle>
          <DialogDescription>{t("table.description")}</DialogDescription>
        </DialogHeader>
        <TableOptions draft={draft} update={update} />
        <TableGrid draft={draft} update={update} />
        <div className="space-y-1">
          <p className="text-small font-medium">{t("table.preview")}</p>
          <pre
            aria-label={t("table.preview")}
            className="max-h-48 overflow-auto rounded border bg-muted p-2 font-mono text-small"
          >
            {code}
          </pre>
        </div>
        <PackageHint
          pkg={draft.style === "booktabs" ? "booktabs" : undefined}
          mainText={mainText}
          view={view}
        />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {t("table.cancel")}
          </Button>
          <Button onClick={insert}>{t("table.insert")}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
