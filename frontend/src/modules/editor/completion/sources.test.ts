import {
  type Completion,
  type CompletionResult,
  type CompletionSource,
  CompletionContext,
} from "@codemirror/autocomplete";
import { EditorState } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { afterEach, describe, expect, it } from "vitest";

import { guarded } from "./extension";
import { RecentUses, type Apply } from "./option";
import { bibSource, citationDetail, firstAuthorSurname } from "./sources/bib";
import { commandSource } from "./sources/commands";
import { environmentSource } from "./sources/environments";
import { bibResourceSource, bibliographySource, graphicsSource, inputSource } from "./sources/files";
import { packageSource } from "./sources/packages";
import { labelSource } from "./sources/refs";
import type { CompletionData, SourceEnv } from "./types";

const DATA: CompletionData = {
  labels: [{ name: "fig:plot", docId: "d2", path: "figures.tex", section: "Results", line: 4 }],
  bib: [
    { key: "silva2023", type: "article", title: "Deep", author: "Silva, A.", year: "2023", path: "refs.bib" },
    { key: "dup", type: "book", path: "refs.bib", alsoIn: ["other.bib"] },
  ],
  files: [
    { path: "main.tex", type: "doc" },
    { path: "chapters/intro.tex", type: "doc" },
    { path: "refs.bib", type: "doc" },
    { path: "images/plot.png", type: "file" },
    { path: "notes.txt", type: "file" },
  ],
};

function envFor(data: CompletionData = DATA): SourceEnv {
  return { data: { current: data }, recent: new RecentUses() };
}

/** Runs a source with the cursor where the `▮` marker is. */
async function complete(source: CompletionSource, doc: string): Promise<CompletionResult | null> {
  const pos = doc.indexOf("▮");
  const state = EditorState.create({ doc: doc.replace("▮", "") });
  return (await source(new CompletionContext(state, pos, false))) ?? null;
}

function labels(result: CompletionResult | null): string[] {
  return result?.options.map((option) => option.label) ?? [];
}

function optionNamed(result: CompletionResult | null, label: string): Completion {
  const option = result?.options.find((candidate) => candidate.label === label);
  if (!option) throw new Error(`no completion ${label}`);
  return option;
}

let view: EditorView | null = null;
afterEach(() => {
  view?.destroy();
  view = null;
});

/** Accepts `option` in a real editor that holds `text`, replacing `from`..end. */
function accept(text: string, option: Completion, from: number): EditorView {
  view = new EditorView({ state: EditorState.create({ doc: text }), parent: document.body });
  (option.apply as Apply)(view, option, from, text.length);
  return view;
}

describe("commands", () => {
  it("offers commands after a backslash and inserts a snippet with the cursor between the braces", async () => {
    const result = await complete(commandSource(envFor()), "\\sec▮");
    expect(labels(result)).toContain("\\section");
    const editor = accept("\\sec", optionNamed(result, "\\section"), result!.from);
    expect(editor.state.doc.toString()).toBe("\\section{}");
    expect(editor.state.selection.main.head).toBe("\\section{".length);
  });

  it("shows the hint and the package a command needs", async () => {
    const result = await complete(commandSource(envFor()), "\\toprule▮");
    const option = optionNamed(result, "\\toprule");
    expect(option.detail).toBe("Top rule of a table");
    expect(option.info).toBe("\\usepackage{booktabs}");
  });

  it("inserts a command without a snippet as plain text", async () => {
    const result = await complete(commandSource(envFor()), "\\maketi▮");
    const editor = accept("\\maketi", optionNamed(result, "\\maketitle"), result!.from);
    expect(editor.state.doc.toString()).toBe("\\maketitle");
  });

  it("offers nothing without a backslash", async () => {
    expect(await complete(commandSource(envFor()), "plain ▮")).toBeNull();
  });

  it("ranks a command used before first among equal matches", async () => {
    const env = envFor();
    const first = await complete(commandSource(env), "\\sec▮");
    const editor = accept("\\sec", optionNamed(first, "\\section"), first!.from);
    expect(editor).toBeDefined();
    const again = await complete(commandSource(env), "\\sec▮");
    expect(optionNamed(again, "\\section").boost).toBe(1);
    expect(optionNamed(again, "\\subsection").boost ?? 0).toBe(0);
  });
});

describe("environments", () => {
  it("offers environment names after \\begin{", async () => {
    const result = await complete(environmentSource(envFor()), "\\begin{fig▮");
    expect(labels(result)).toEqual(expect.arrayContaining(["figure", "table", "itemize"]));
  });

  it("writes the whole block, replacing \\begin{ already typed, with the cursor in its first field", async () => {
    const result = await complete(environmentSource(envFor()), "\\begin{fig▮");
    const editor = accept("\\begin{fig", optionNamed(result, "figure"), result!.from);
    const text = editor.state.doc.toString();
    expect(text.startsWith("\\begin{figure}[htbp]")).toBe(true);
    expect(text.endsWith("\\end{figure}")).toBe(true);
    expect(text).toContain("\\caption{");
    expect(text).toContain("\\label{fig:");
    const head = editor.state.selection.main.head;
    expect(head).toBeGreaterThan(0);
    expect(head).toBeLessThan(text.indexOf("\\end{figure}"));
  });
});

describe("bibliography keys", () => {
  it("offers keys after \\cite{ with title, first author and year", async () => {
    const result = await complete(bibSource(envFor()), "\\cite{si▮");
    expect(labels(result)).toContain("silva2023");
    expect(optionNamed(result, "silva2023").detail).toBe("— Deep — Silva, 2023");
  });

  it("offers keys again after a comma inside the citation", async () => {
    const result = await complete(bibSource(envFor()), "\\cite{silva2023, ▮");
    expect(labels(result)).toEqual(expect.arrayContaining(["silva2023", "dup"]));
    expect(result?.from).toBe("\\cite{silva2023, ".length);
  });

  it("uses the other citation commands too", async () => {
    for (const command of [
      "\\citep{",
      "\\citet{",
      "\\parencite{",
      "\\textcite{",
      "\\autocite{",
      "\\nocite{",
    ]) {
      expect(labels(await complete(bibSource(envFor()), `${command}▮`))).toContain("silva2023");
    }
  });

  it("hints where a key is also defined", async () => {
    const result = await complete(bibSource(envFor()), "\\cite{d▮");
    expect(optionNamed(result, "dup").info).toContain("other.bib");
  });

  it("reads the surname and the detail of a citation", () => {
    expect(firstAuthorSurname("Silva, A. and Souza, B.")).toBe("Silva");
    expect(firstAuthorSurname("Ana Maria Silva")).toBe("Silva");
    expect(firstAuthorSurname(undefined)).toBeUndefined();
    expect(citationDetail({ key: "k", type: "misc", path: "a.bib" })).toBeUndefined();
  });
});

describe("references", () => {
  it.each(["\\ref{fig▮", "\\eqref{fig▮", "\\autoref{fig▮", "\\cref{fig▮", "\\Cref{fig▮", "\\pageref{fig▮"])(
    "offers labels from every file after %s",
    async (doc) => {
      const result = await complete(labelSource(envFor()), doc);
      expect(labels(result)).toEqual(["fig:plot"]);
      expect(optionNamed(result, "fig:plot").detail).toBe("Results");
      expect(optionNamed(result, "fig:plot").info).toBe("figures.tex");
    },
  );
});

describe("project files", () => {
  it("offers .tex files without the extension for \\input", async () => {
    const result = await complete(inputSource(envFor()), "\\input{▮");
    expect(labels(result)).toEqual(["main", "chapters/intro"]);
  });

  it("offers only images and PDFs for \\includegraphics, with the extension", async () => {
    expect(labels(await complete(graphicsSource(envFor()), "\\includegraphics{▮"))).toEqual([
      "images/plot.png",
    ]);
    expect(labels(await complete(graphicsSource(envFor()), "\\includegraphics[width=3cm]{▮"))).toEqual([
      "images/plot.png",
    ]);
  });

  it("offers .bib files, without the extension for \\bibliography and with it for \\addbibresource", async () => {
    expect(labels(await complete(bibliographySource(envFor()), "\\bibliography{▮"))).toEqual(["refs"]);
    expect(labels(await complete(bibResourceSource(envFor()), "\\addbibresource{▮"))).toEqual(["refs.bib"]);
  });
});

describe("packages", () => {
  it("offers package names after \\usepackage{ and after a comma inside it", async () => {
    expect(labels(await complete(packageSource(envFor()), "\\usepackage{ams▮"))).toEqual(
      expect.arrayContaining(["amsmath", "amssymb"]),
    );
    expect(labels(await complete(packageSource(envFor()), "\\usepackage{amsmath, hyp▮"))).toContain(
      "hyperref",
    );
  });
});

describe("comments and verbatim environments", () => {
  const sources: [string, CompletionSource][] = [
    ["commands", commandSource(envFor())],
    ["environments", environmentSource(envFor())],
    ["citations", bibSource(envFor())],
    ["references", labelSource(envFor())],
    ["inputs", inputSource(envFor())],
    ["packages", packageSource(envFor())],
  ];

  it.each(sources)("%s stay silent inside a comment", async (_name, source) => {
    expect(await complete(guarded(source), "% \\sec▮")).toBeNull();
    expect(await complete(guarded(source), "% \\begin{fig▮")).toBeNull();
    expect(await complete(guarded(source), "% \\cite{si▮")).toBeNull();
  });

  it.each(sources)("%s stay silent inside a verbatim environment", async (_name, source) => {
    expect(await complete(guarded(source), "\\begin{verbatim}\n\\sec▮")).toBeNull();
    expect(await complete(guarded(source), "\\begin{verbatim}\n\\cite{si▮")).toBeNull();
  });

  it("speak again once the comment or the verbatim environment is over", async () => {
    expect(
      labels(await complete(guarded(commandSource(envFor())), "\\begin{verbatim}x\\end{verbatim}\\sec▮")),
    ).toContain("\\section");
  });
});
