import type { ClipboardEvent } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

import { isGridText, parseGridText } from "./paste";
import {
  addColumn,
  addRow,
  pasteGrid,
  removeColumn,
  removeRow,
  setCell,
  setColumn,
  type ColumnAlign,
  type TableColumn,
  type TableDraft,
} from "./table-model";

export type UpdateDraft = (change: (draft: TableDraft) => TableDraft) => void;

const ALIGNS: ColumnAlign[] = ["l", "c", "r", "p"];

function ColumnHead({ column, index, update }: { column: TableColumn; index: number; update: UpdateDraft }) {
  const { t } = useTranslation("insert");
  const number = index + 1;
  return (
    <th scope="col" className="align-bottom font-normal">
      <div className="flex flex-col items-stretch gap-1">
        <select
          aria-label={t("table.columnAlign", { column: number })}
          value={column.align}
          onChange={(event) =>
            update((draft) => setColumn(draft, index, { align: event.target.value as ColumnAlign }))
          }
          className="h-8 rounded border bg-background px-1 text-small"
        >
          {ALIGNS.map((align) => (
            <option key={align} value={align}>
              {t(`table.align.${align}`)}
            </option>
          ))}
        </select>
        {column.align === "p" && (
          <Input
            aria-label={t("table.columnWidth", { column: number })}
            value={column.width}
            onChange={(event) => update((draft) => setColumn(draft, index, { width: event.target.value }))}
            className="h-8 text-small"
          />
        )}
        <Button
          variant="ghost"
          size="sm"
          aria-label={t("table.removeColumn", { column: number })}
          onClick={() => update((draft) => removeColumn(draft, index))}
        >
          ×
        </Button>
      </div>
    </th>
  );
}

function pasteCells(
  event: ClipboardEvent<HTMLInputElement>,
  row: number,
  column: number,
  update: UpdateDraft,
) {
  const text = event.clipboardData.getData("text/plain");
  if (!isGridText(text)) return;
  event.preventDefault();
  const grid = parseGridText(text);
  update((draft) => pasteGrid(draft, row, column, grid));
}

/** The editable grid: one input per cell, so Tab moves between cells, and a paste fills from the focused cell. */
export function TableGrid({ draft, update }: { draft: TableDraft; update: UpdateDraft }) {
  const { t } = useTranslation("insert");
  return (
    <div className="space-y-2 overflow-x-auto">
      <table className="border-separate border-spacing-1">
        <thead>
          <tr>
            <th scope="col" className="w-10">
              <span className="sr-only">{t("table.rows")}</span>
            </th>
            {draft.columns.map((column, c) => (
              <ColumnHead key={c} column={column} index={c} update={update} />
            ))}
          </tr>
        </thead>
        <tbody>
          {draft.cells.map((row, r) => (
            <tr key={r}>
              <th scope="row" className="font-normal">
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={t("table.removeRow", { row: r + 1 })}
                  onClick={() => update((current) => removeRow(current, r))}
                >
                  ×
                </Button>
              </th>
              {row.map((value, c) => (
                <td key={c}>
                  <Input
                    aria-label={t("table.cellLabel", { row: r + 1, column: c + 1 })}
                    value={value}
                    onChange={(event) => update((current) => setCell(current, r, c, event.target.value))}
                    onPaste={(event) => pasteCells(event, r, c, update)}
                    className="h-8 min-w-24 text-small"
                  />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="flex gap-2">
        <Button variant="outline" size="sm" onClick={() => update(addRow)}>
          {t("table.addRow")}
        </Button>
        <Button variant="outline" size="sm" onClick={() => update(addColumn)}>
          {t("table.addColumn")}
        </Button>
      </div>
    </div>
  );
}
