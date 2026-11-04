/** Whether clipboard text is a block of cells: tab or line separated, the way spreadsheets copy. */
export function isGridText(text: string): boolean {
  return /[\t\n]/.test(text.replace(/\r?\n$/, ""));
}

/**
 * Splits spreadsheet text into rows of cells. A cell in double quotes may hold tabs and line breaks, and `""`
 * inside quotes is one quote, as Excel and Sheets write them. Trailing empty rows are dropped.
 */
export function parseGridText(text: string): string[][] {
  const source = text.replace(/\r\n?/g, "\n");
  const rows: string[][] = [];
  let row: string[] = [];
  let field = "";
  let quoted = false;
  for (let i = 0; i < source.length; i++) {
    const char = source[i]!;
    if (quoted) {
      if (char !== '"') field += char;
      else if (source[i + 1] === '"') {
        field += '"';
        i++;
      } else quoted = false;
    } else if (char === '"' && field === "") quoted = true;
    else if (char === "\t") {
      row.push(field);
      field = "";
    } else if (char === "\n") {
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else field += char;
  }
  if (field !== "" || row.length > 0) rows.push([...row, field]);
  while (rows.length > 0 && rows[rows.length - 1]!.every((cell) => cell === "")) rows.pop();
  return rows;
}
