import type { CompletionSource } from "@codemirror/autocomplete";

import { ARGUMENT_PATTERN, REF_COMMANDS, argumentToken } from "../context";
import { toOption } from "../option";
import type { SourceEnv } from "../types";

/**
 * `\ref{` and the other reference commands offer every `\label` of the project, from any file, with the section it
 * falls under and the file it is in.
 */
export function labelSource(env: SourceEnv): CompletionSource {
  return (context) => {
    const token = argumentToken(context, REF_COMMANDS);
    if (!token) return null;
    return {
      from: token.from,
      validFor: ARGUMENT_PATTERN,
      options: env.data.current.labels.map((label) =>
        toOption(env.recent, {
          key: `ref:${label.name}`,
          label: label.name,
          apply: label.name,
          detail: label.section,
          info: label.path,
          type: "variable",
        }),
      ),
    };
  };
}
