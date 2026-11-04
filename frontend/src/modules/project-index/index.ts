/** The module's public interface: the editor, and the autocomplete of spec 112, import only from here. */
export { findCurrentEntry } from "./current-entry";
export { SECTION_LEVELS, parseStructure } from "./parse-structure";
export type { StructureItem, StructureKind } from "./parse-structure";
export { resolveIncludes } from "./resolve-includes";
export type { IndexedDoc, ResolvedItem } from "./resolve-includes";
export { useProjectIndex } from "./use-project-index";
export type { IndexStatus, ProjectIndex } from "./use-project-index";
