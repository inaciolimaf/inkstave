import type { CompletionSource } from "@codemirror/autocomplete";

import { commandToken } from "../context";
import { loadStaticData } from "../load-data";
import { insertSnippet, insertText, toOption } from "../option";
import type { SourceEnv } from "../types";

const COMMAND_PATTERN = /^\\[A-Za-z]*$/;

/** `\` and letters offer every command of the static list, with its snippet and the package it needs. */
export function commandSource(env: SourceEnv): CompletionSource {
  return async (context) => {
    const token = commandToken(context);
    if (!token) return null;
    const { commands } = await loadStaticData();
    if (context.aborted) return null;
    return {
      from: token.from,
      validFor: COMMAND_PATTERN,
      options: commands.map((entry) =>
        toOption(env.recent, {
          key: `cmd:${entry.name}`,
          label: `\\${entry.name}`,
          apply: entry.snippet ? insertSnippet(entry.snippet) : insertText(`\\${entry.name}`),
          detail: entry.hint,
          info: entry.package ? `\\usepackage{${entry.package}}` : undefined,
          type: "keyword",
        }),
      ),
    };
  };
}
