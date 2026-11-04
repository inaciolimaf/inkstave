import type { CompletionSource } from "@codemirror/autocomplete";

import i18n from "@/i18n/config";
import type { BibRef } from "@/modules/project-index";

import { ARGUMENT_PATTERN, CITE_COMMANDS, argumentToken } from "../context";
import { toOption } from "../option";
import type { SourceEnv } from "../types";

/** The first author's surname: `Silva, A. and Souza, B.` reads `Silva`; `Ana Silva` reads `Silva`. */
export function firstAuthorSurname(author: string | undefined): string | undefined {
  if (!author) return undefined;
  const first = author.split(/\s+and\s+/i)[0].trim();
  const surname = first.includes(",") ? first.slice(0, first.indexOf(",")) : first.split(" ").pop();
  return surname?.trim() || undefined;
}

/** `— Title — Surname, 2023`: what the list shows after the key. */
export function citationDetail(ref: BibRef): string | undefined {
  const who = [firstAuthorSurname(ref.author), ref.year].filter(Boolean).join(", ");
  const body = [ref.title, who].filter(Boolean).join(" — ");
  return body ? `— ${body}` : undefined;
}

/**
 * `\cite{`, `\citep{` and the other citation commands, and after a comma inside them, offer the keys of the
 * project's `.bib` files. A key that two files define is listed once, with a hint naming the other file.
 */
export function bibSource(env: SourceEnv): CompletionSource {
  return (context) => {
    const token = argumentToken(context, CITE_COMMANDS);
    if (!token) return null;
    return {
      from: token.from,
      validFor: ARGUMENT_PATTERN,
      options: env.data.current.bib.map((ref) =>
        toOption(env.recent, {
          key: `cite:${ref.key}`,
          label: ref.key,
          apply: ref.key,
          detail: citationDetail(ref),
          info: ref.alsoIn ? i18n.t("editor:completion.alsoIn", { file: ref.alsoIn.join(", ") }) : undefined,
          type: "constant",
        }),
      ),
    };
  };
}
