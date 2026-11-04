/** The table builder's draft (spec 114 §5.3). Every function returns a new draft and keeps the limits. */
export type ColumnAlign = "l" | "c" | "r" | "p";
export type TableStyle = "booktabs" | "grid";

export interface TableColumn {
  align: ColumnAlign;
  /** The width of a `p` column, as a dimension such as `3cm` or `0.3\textwidth`. */
  width: string;
}

export interface TableDraft {
  /** Row-major cell text; every row has one entry per column. */
  cells: string[][];
  columns: TableColumn[];
  header: boolean;
  style: TableStyle;
  caption: string;
  label: string;
  placement: string;
  cellsAreLatex: boolean;
}

export const MAX_ROWS = 30;
export const MAX_COLUMNS = 15;
export const DEFAULT_WIDTH = "3cm";
const START = 3;

const blankRow = (columns: number) => Array.from({ length: columns }, () => "");
const newColumn = (): TableColumn => ({ align: "l", width: DEFAULT_WIDTH });

export function emptyTable(rows = START, columns = START): TableDraft {
  return {
    cells: Array.from({ length: rows }, () => blankRow(columns)),
    columns: Array.from({ length: columns }, newColumn),
    header: true,
    style: "booktabs",
    caption: "",
    label: "tab:",
    placement: "htbp",
    cellsAreLatex: false,
  };
}

export function addRow(draft: TableDraft): TableDraft {
  if (draft.cells.length >= MAX_ROWS) return draft;
  return { ...draft, cells: [...draft.cells, blankRow(draft.columns.length)] };
}

export function removeRow(draft: TableDraft, index: number): TableDraft {
  if (draft.cells.length <= 1) return draft;
  return { ...draft, cells: draft.cells.filter((_, i) => i !== index) };
}

export function addColumn(draft: TableDraft): TableDraft {
  if (draft.columns.length >= MAX_COLUMNS) return draft;
  return {
    ...draft,
    columns: [...draft.columns, newColumn()],
    cells: draft.cells.map((row) => [...row, ""]),
  };
}

export function removeColumn(draft: TableDraft, index: number): TableDraft {
  if (draft.columns.length <= 1) return draft;
  return {
    ...draft,
    columns: draft.columns.filter((_, i) => i !== index),
    cells: draft.cells.map((row) => row.filter((_, i) => i !== index)),
  };
}

export function setCell(draft: TableDraft, row: number, column: number, value: string): TableDraft {
  const cells = draft.cells.map((cellRow, r) =>
    r === row ? cellRow.map((cell, c) => (c === column ? value : cell)) : cellRow,
  );
  return { ...draft, cells };
}

export function setColumn(draft: TableDraft, index: number, patch: Partial<TableColumn>): TableDraft {
  const columns = draft.columns.map((column, i) => (i === index ? { ...column, ...patch } : column));
  return { ...draft, columns };
}

/** Writes pasted rows from a cell onward, growing the grid up to its limits. */
export function pasteGrid(draft: TableDraft, row: number, column: number, pasted: string[][]): TableDraft {
  const rows = Math.min(MAX_ROWS, Math.max(draft.cells.length, row + pasted.length));
  const widest = Math.max(0, ...pasted.map((line) => line.length));
  const columns = Math.min(MAX_COLUMNS, Math.max(draft.columns.length, column + widest));
  const cells = Array.from({ length: rows }, (_, r) =>
    Array.from({ length: columns }, (_, c) => draft.cells[r]?.[c] ?? ""),
  );
  pasted.forEach((line, dr) =>
    line.forEach((value, dc) => {
      const r = row + dr;
      const c = column + dc;
      if (r < rows && c < columns) cells[r]![c] = value;
    }),
  );
  const grown = Array.from({ length: columns }, (_, c) => draft.columns[c] ?? newColumn());
  return { ...draft, cells, columns: grown };
}
