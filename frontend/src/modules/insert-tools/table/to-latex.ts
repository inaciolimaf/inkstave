import { DEFAULT_WIDTH, type TableColumn, type TableDraft, type TableStyle } from "./table-model";

const SPECIAL: Record<string, string> = {
  "&": "\\&",
  "%": "\\%",
  $: "\\$",
  "#": "\\#",
  _: "\\_",
  "{": "\\{",
  "}": "\\}",
  "~": "\\textasciitilde{}",
  "^": "\\textasciicircum{}",
  "\\": "\\textbackslash{}",
};

/** Escapes plain text so that LaTeX prints it as typed. One pass, so an escape is never escaped again. */
export function escapeLatex(text: string): string {
  return text.replace(/[&%$#_{}~^\\]/g, (char) => SPECIAL[char] ?? char);
}

const WIDTH = /^(\d*\.?\d+(cm|mm|in|pt|em|ex)|\d*\.?\d*\\(textwidth|linewidth|columnwidth))$/;

/** A width the `p` column accepts; anything else falls back to the default, so the code always compiles. */
export function safeWidth(width: string): string {
  const trimmed = width.trim();
  return WIDTH.test(trimmed) ? trimmed : DEFAULT_WIDTH;
}

/** The label a caption suggests: `tab:` and the caption's words, lower case, without accents. */
export function labelFor(caption: string): string {
  const slug = caption
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return `tab:${slug}`;
}

function columnSpec(columns: TableColumn[], style: TableStyle): string {
  const specs = columns.map((column) =>
    column.align === "p" ? `p{${safeWidth(column.width)}}` : column.align,
  );
  return style === "grid" ? `|${specs.join("|")}|` : specs.join("");
}

function text(value: string, asLatex: boolean): string {
  const oneLine = value.trim().replace(/\s*\n\s*/g, " ");
  return asLatex ? oneLine : escapeLatex(oneLine);
}

/** The rows between the rules: booktabs puts a midrule under the header, the grid a rule under every row. */
function ruledRows(draft: TableDraft): string[] {
  const rows = draft.cells.map(
    (row) => `${row.map((cell) => text(cell, draft.cellsAreLatex)).join(" & ")} \\\\`,
  );
  if (draft.style === "grid") return ["\\hline", ...rows.flatMap((row) => [row, "\\hline"])];
  const lines = ["\\toprule"];
  rows.forEach((row, index) => {
    lines.push(row);
    if (index === 0 && draft.header) lines.push("\\midrule");
  });
  lines.push("\\bottomrule");
  return lines;
}

/** The float and its tabular, as the builder's options describe them (spec 114 §5.3). */
export function tableToLatex(draft: TableDraft): string {
  const placement = draft.placement.trim();
  const lines = [`\\begin{table}${placement ? `[${placement}]` : ""}`, "  \\centering"];
  if (draft.caption.trim()) lines.push(`  \\caption{${text(draft.caption, draft.cellsAreLatex)}}`);
  if (draft.label.trim()) lines.push(`  \\label{${draft.label.trim()}}`);
  lines.push(`  \\begin{tabular}{${columnSpec(draft.columns, draft.style)}}`);
  lines.push(...ruledRows(draft).map((line) => `    ${line}`));
  lines.push("  \\end{tabular}", "\\end{table}");
  return lines.join("\n");
}
