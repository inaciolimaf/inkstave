import type { CompletionSource } from "@codemirror/autocomplete";

import { BEGIN_PREFIX, environmentToken } from "../context";
import { loadStaticData } from "../load-data";
import { insertSnippet, toOption } from "../option";
import type { SourceEnv } from "../types";

const NAME_PATTERN = /^[\w*-]*$/;

/**
 * `\begin{` and letters offer the environments. Choosing one writes the whole block with the cursor in its first
 * field; the block replaces the `\begin{` already typed.
 */
export function environmentSource(env: SourceEnv): CompletionSource {
  return async (context) => {
    const token = environmentToken(context);
    if (!token) return null;
    const { environments } = await loadStaticData();
    if (context.aborted) return null;
    return {
      from: token.from,
      validFor: NAME_PATTERN,
      options: environments.map((entry) => {
        const insert = insertSnippet(entry.snippet.replaceAll("@NAME@", entry.name));
        return toOption(env.recent, {
          key: `env:${entry.name}`,
          label: entry.name,
          apply: (view, completion, from, to) => insert(view, completion, from - BEGIN_PREFIX.length, to),
          detail: entry.hint,
          info: entry.package ? `\\usepackage{${entry.package}}` : undefined,
          type: "namespace",
        });
      }),
    };
  };
}
