/** The module's public interface (spec 122): the editor imports only from here. */
export type { TextMatch } from "./find";
export type { TextEdit } from "./replace";
export { applyEdits } from "./replace";
export type { TextWriter } from "./replace-actions";
export type { SourceText } from "./search-project";
export { SearchPanel } from "./search-panel";
export type { SearchPanelProps, SearchStatus } from "./search-panel";
export type { MatchTarget } from "./search-results";
export { useProjectSearch } from "./use-project-search";
export type { ProjectSearchState } from "./use-project-search";
