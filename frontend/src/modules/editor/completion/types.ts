import type { RefObject } from "react";

import type { BibRef, LabelRef, ProjectFile } from "@/modules/project-index";

import type { RecentUses } from "./option";

/** A LaTeX command from `data/commands.json`. `snippet` is the text to insert, backslash included, with fields. */
export interface CommandEntry {
  name: string;
  snippet?: string;
  hint: string;
  package?: string;
}

/** An environment from `data/environments.json`. `snippet` is the whole block; `@NAME@` stands for its name. */
export interface EnvironmentEntry {
  name: string;
  snippet: string;
  hint: string;
  package?: string;
}

/** The static part of the completion data, loaded the first time completion opens. */
export interface StaticData {
  commands: CommandEntry[];
  environments: EnvironmentEntry[];
  packages: string[];
}

/** The project part, from the project index (spec 111, extended by spec 112). */
export interface CompletionData {
  labels: LabelRef[];
  bib: BibRef[];
  files: ProjectFile[];
}

export const EMPTY_COMPLETION_DATA: CompletionData = { labels: [], bib: [], files: [] };

/** What every source reads: the project data, which changes as the writer types, and the recency of this editor. */
export interface SourceEnv {
  data: RefObject<CompletionData>;
  recent: RecentUses;
}
