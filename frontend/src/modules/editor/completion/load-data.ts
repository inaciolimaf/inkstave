import type { CommandEntry, EnvironmentEntry, StaticData } from "./types";

let loaded: Promise<StaticData> | null = null;

/**
 * The static completion data, imported the first time completion runs (spec 112). The JSON files are dynamic
 * imports, so they are separate chunks and stay out of the initial bundle. One promise serves every editor.
 */
export function loadStaticData(): Promise<StaticData> {
  loaded ??= Promise.all([
    import("./data/commands.json"),
    import("./data/environments.json"),
    import("./data/packages.json"),
  ]).then(([commands, environments, packages]) => ({
    commands: commands.default as CommandEntry[],
    environments: environments.default as EnvironmentEntry[],
    packages: packages.default as string[],
  }));
  return loaded;
}
