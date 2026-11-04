import type { CompletionSource } from "@codemirror/autocomplete";

import { ARGUMENT_PATTERN, GRAPHICS_COMMANDS, INPUT_COMMANDS, argumentToken } from "../context";
import { toOption } from "../option";
import type { SourceEnv } from "../types";

const IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg", ".pdf", ".eps", ".svg"];

/** A file path that one of the commands can use, and what it inserts for it. */
interface PathRule {
  commands: readonly string[];
  accepts: (path: string) => boolean;
  insert: (path: string) => string;
}

const hasExtension = (path: string, extensions: readonly string[]) =>
  extensions.some((extension) => path.toLowerCase().endsWith(extension));
const dropExtension = (path: string, extension: string) => path.slice(0, -extension.length);

/**
 * Project files for one command family. The list shows the paths the command takes: `\input` takes a `.tex` path
 * without its extension, `\bibliography` a `.bib` path without it, `\includegraphics` an image with it.
 */
export function pathSource(env: SourceEnv, rule: PathRule): CompletionSource {
  return (context) => {
    const token = argumentToken(context, rule.commands);
    if (!token) return null;
    return {
      from: token.from,
      validFor: ARGUMENT_PATTERN,
      options: env.data.current.files
        .filter((file) => rule.accepts(file.path))
        .map((file) =>
          toOption(env.recent, {
            key: `path:${file.path}`,
            label: rule.insert(file.path),
            apply: rule.insert(file.path),
            type: "text",
          }),
        ),
    };
  };
}

/** `\input{`, `\include{`, `\subfile{`: the `.tex` files of the project. */
export function inputSource(env: SourceEnv): CompletionSource {
  return pathSource(env, {
    commands: INPUT_COMMANDS,
    accepts: (path) => hasExtension(path, [".tex"]),
    insert: (path) => dropExtension(path, ".tex"),
  });
}

/** `\includegraphics{`: the image and PDF files of the project, with their extensions. */
export function graphicsSource(env: SourceEnv): CompletionSource {
  return pathSource(env, {
    commands: GRAPHICS_COMMANDS,
    accepts: (path) => hasExtension(path, IMAGE_EXTENSIONS),
    insert: (path) => path,
  });
}

/** `\bibliography{`: the `.bib` files, without the extension the command adds. */
export function bibliographySource(env: SourceEnv): CompletionSource {
  return pathSource(env, {
    commands: ["bibliography"],
    accepts: (path) => hasExtension(path, [".bib"]),
    insert: (path) => dropExtension(path, ".bib"),
  });
}

/** `\addbibresource{`: the `.bib` files, with their extension, which this command needs. */
export function bibResourceSource(env: SourceEnv): CompletionSource {
  return pathSource(env, {
    commands: ["addbibresource"],
    accepts: (path) => hasExtension(path, [".bib"]),
    insert: (path) => path,
  });
}
