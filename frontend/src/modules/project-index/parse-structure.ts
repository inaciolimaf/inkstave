/**
 * Pure LaTeX structure parser (spec 111): the sections, labels and includes of one file, in document order,
 * each with its 1-based line. No DOM, no network: the outline and the autocomplete (spec 112) both read it.
 */

export type StructureKind = "section" | "label" | "include";

export interface StructureItem {
  kind: StructureKind;
  /** Sectioning depth, `part` 0 to `subparagraph` 6. Sections only. */
  level?: number;
  /** A section's long title (the optional short title is dropped), or a label's name. */
  title?: string;
  /** An include's path as the project sees it. `\import{dir}{x}` joins the two. */
  target?: string;
  /** 1-based line of the command. */
  line: number;
}

export const SECTION_LEVELS: Readonly<Record<string, number>> = {
  part: 0,
  chapter: 1,
  section: 2,
  subsection: 3,
  subsubsection: 4,
  paragraph: 5,
  subparagraph: 6,
};

const INCLUDE_COMMANDS = new Set(["input", "include", "subfile"]);

/** An unescaped `%` to the end of its line. */
const COMMENT = /(?<!\\)%[^\n]*/g;
/** Environments whose body is not LaTeX. */
const OPAQUE_ENVIRONMENT = /\\begin\{(verbatim\*?|lstlisting|minted|comment)\}[\s\S]*?\\end\{\1\}/g;
const COMMAND = /\\([a-zA-Z]+)\*?/g;

/** Blanks every match but keeps its newlines, so the line numbers of the text stay the same. */
function blank(text: string, pattern: RegExp): string {
  return text.replace(pattern, (match) => match.replace(/[^\n]/g, " "));
}

/** Reads the `{...}` argument that starts at or after `from`, with its nested braces. */
function braceArg(text: string, from: number): { value: string; end: number } | null {
  const open = /\s*\{/y;
  open.lastIndex = from;
  const match = open.exec(text);
  if (!match) return null;
  const start = from + match[0].length - 1;
  let depth = 0;
  for (let i = start; i < text.length; i++) {
    if (text[i] === "{") depth++;
    else if (text[i] === "}" && --depth === 0) return { value: text.slice(start + 1, i), end: i + 1 };
  }
  return null;
}

/** Skips an optional `[...]` argument (a short title) at or after `from`. */
function skipOptional(text: string, from: number): number {
  const optional = /\s*\[[^\]]*\]/y;
  optional.lastIndex = from;
  const match = optional.exec(text);
  return match ? from + match[0].length : from;
}

function squash(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

function sectionItem(text: string, name: string, after: number, line: number): StructureItem | null {
  const arg = braceArg(text, skipOptional(text, after));
  if (!arg) return null;
  return { kind: "section", level: SECTION_LEVELS[name], title: squash(arg.value), line };
}

function importItem(text: string, after: number, line: number): StructureItem | null {
  const dir = braceArg(text, after);
  if (!dir) return null;
  const file = braceArg(text, dir.end);
  if (!file) return null;
  const folder = dir.value.trim().replace(/\/+$/, "");
  const name = file.value.trim();
  return { kind: "include", target: folder ? `${folder}/${name}` : name, line };
}

/** The item a command starts, if it is one the outline or the index keeps. */
function commandItem(text: string, name: string, after: number, line: number): StructureItem | null {
  if (Object.hasOwn(SECTION_LEVELS, name)) return sectionItem(text, name, after, line);
  if (INCLUDE_COMMANDS.has(name)) {
    const arg = braceArg(text, after);
    return arg ? { kind: "include", target: arg.value.trim(), line } : null;
  }
  if (name === "import") return importItem(text, after, line);
  if (name === "label") {
    const arg = braceArg(text, after);
    return arg ? { kind: "label", title: arg.value.trim(), line } : null;
  }
  return null;
}

function countNewlines(text: string, from: number, to: number): number {
  let count = 0;
  for (let i = from; i < to; i++) if (text[i] === "\n") count++;
  return count;
}

/** Every sectioning command, label and include of `text`, in document order. */
export function parseStructure(text: string): StructureItem[] {
  const masked = blank(blank(text, COMMENT), OPAQUE_ENVIRONMENT);
  const items: StructureItem[] = [];
  const commands = new RegExp(COMMAND.source, "g");
  let line = 1;
  let counted = 0;
  for (let match = commands.exec(masked); match; match = commands.exec(masked)) {
    line += countNewlines(masked, counted, match.index);
    counted = match.index;
    const item = commandItem(masked, match[1], match.index + match[0].length, line);
    if (item) items.push(item);
  }
  return items;
}
