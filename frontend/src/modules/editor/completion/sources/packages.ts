import type { CompletionSource } from "@codemirror/autocomplete";

import { ARGUMENT_PATTERN, PACKAGE_COMMANDS, argumentToken } from "../context";
import { loadStaticData } from "../load-data";
import { toOption } from "../option";
import type { SourceEnv } from "../types";

/** `\usepackage{` and `\RequirePackage{`, and after a comma inside them, offer the package names. */
export function packageSource(env: SourceEnv): CompletionSource {
  return async (context) => {
    const token = argumentToken(context, PACKAGE_COMMANDS);
    if (!token) return null;
    const { packages } = await loadStaticData();
    if (context.aborted) return null;
    return {
      from: token.from,
      validFor: ARGUMENT_PATTERN,
      options: packages.map((name) =>
        toOption(env.recent, { key: `pkg:${name}`, label: name, apply: name, type: "module" }),
      ),
    };
  };
}
