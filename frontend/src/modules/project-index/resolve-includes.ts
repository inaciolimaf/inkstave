/**
 * Orders the project's structure the way LaTeX reads it: from the main document, following each include in
 * place (spec 111). Every file is taken once, so a cycle ends where it started.
 */
import type { StructureItem } from "./parse-structure";

/** A project document as the index sees it: its tree id, its project path and its parsed structure. */
export interface IndexedDoc {
  id: string;
  path: string;
  items: StructureItem[];
}

/** One structure item, placed in the project: which document it is in and that document's path. */
export interface ResolvedItem extends StructureItem {
  docId: string;
  path: string;
}

/** The include target as a project path: `./` dropped, `.tex` added when the file has no such name. */
function candidatePaths(target: string): string[] {
  const path = target.trim().replace(/^\.\//, "");
  return [path, `${path}.tex`];
}

/** Every item of the main document and of the files it includes, in document order. */
export function resolveIncludes(
  mainDocId: string | null,
  docs: ReadonlyMap<string, IndexedDoc>,
): ResolvedItem[] {
  const byPath = new Map([...docs.values()].map((doc) => [doc.path, doc]));
  const resolved: ResolvedItem[] = [];
  const seen = new Set<string>();

  const visit = (doc: IndexedDoc) => {
    if (seen.has(doc.id)) return;
    seen.add(doc.id);
    for (const item of doc.items) {
      if (item.kind !== "include") {
        resolved.push({ ...item, docId: doc.id, path: doc.path });
        continue;
      }
      const target = candidatePaths(item.target ?? "")
        .map((path) => byPath.get(path))
        .find((found) => found !== undefined);
      if (target) visit(target);
    }
  };

  const main = mainDocId ? docs.get(mainDocId) : undefined;
  if (main) visit(main);
  return resolved;
}
