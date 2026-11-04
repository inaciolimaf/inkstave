import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { applyEdits } from "./replace";
import type { TextWriter } from "./replace-actions";
import { SearchPanel } from "./search-panel";
import type { SourceText } from "./search-project";
import { SEARCH_DEBOUNCE_MS, useProjectSearch } from "./use-project-search";

const SOURCES: SourceText[] = [
  { id: "main", path: "main.tex", text: "\\section{Rede neural}\nUma rede neural.\n" },
  { id: "intro", path: "chapters/intro.tex", text: "Outra rede neural aqui.\n" },
];

function Harness({
  sources,
  writer,
  onOpen,
}: {
  sources: SourceText[];
  writer?: TextWriter;
  onOpen: () => void;
}) {
  const state = useProjectSearch({
    sources,
    openWriter: writer ? () => writer : undefined,
    onWritten: vi.fn(),
  });
  return <SearchPanel state={state} status="ready" onOpen={onOpen} focusKey={0} />;
}

function writerOver(texts: Record<string, string>): TextWriter {
  return {
    async transformContent(path, edit) {
      texts[path] = applyEdits(texts[path], edit(texts[path]));
      return texts[path];
    },
  };
}

async function search(user: ReturnType<typeof userEvent.setup>, query: string) {
  await user.type(screen.getByRole("searchbox", { name: "Search the project" }), query);
  act(() => {
    vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS);
  });
}

describe("SearchPanel", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("lists the matches of every file, grouped by file, and opens one at its place", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const onOpen = vi.fn();
    render(<Harness sources={SOURCES} onOpen={onOpen} />);
    await search(user, "rede neural");
    expect(screen.getByRole("status")).toHaveTextContent("3 results in 2 files");
    expect(screen.getByText("chapters/intro.tex")).toBeInTheDocument();
    expect(screen.getByText("main.tex")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "main.tex, line 2: Uma rede neural." }));
    expect(onOpen).toHaveBeenCalledWith({ path: "main.tex", line: 2, column: 4, length: 11 });
  });

  it("says when nothing matches and when a regular expression is invalid", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<Harness sources={SOURCES} onOpen={vi.fn()} />);
    await search(user, "absent");
    expect(screen.getByRole("status")).toHaveTextContent("No results.");
    await user.clear(screen.getByRole("searchbox"));
    await user.click(screen.getByRole("button", { name: "Use regular expression" }));
    await search(user, "(open");
    expect(screen.getByRole("status")).toHaveTextContent("Invalid regular expression");
  });

  it("replaces all only after a confirmation that counts every match", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const texts = Object.fromEntries(SOURCES.map((s) => [s.path, s.text]));
    render(<Harness sources={SOURCES} writer={writerOver(texts)} onOpen={vi.fn()} />);
    await search(user, "rede neural");
    await user.type(screen.getByRole("textbox", { name: "Replace with" }), "modelo neural");
    await user.click(screen.getByRole("button", { name: "Replace all" }));
    const confirm = screen.getByRole("alertdialog");
    expect(confirm).toHaveTextContent("Replace 3 matches in 2 files?");
    expect(texts["main.tex"]).toContain("rede neural");
    await user.click(within(confirm).getByRole("button", { name: "Replace" }));
    await vi.waitFor(() => expect(texts["main.tex"]).toBe("\\section{modelo neural}\nUma modelo neural.\n"));
    expect(texts["chapters/intro.tex"]).toBe("Outra modelo neural aqui.\n");
  });

  it("replaces a single match from its row", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const texts = Object.fromEntries(SOURCES.map((s) => [s.path, s.text]));
    render(<Harness sources={SOURCES} writer={writerOver(texts)} onOpen={vi.fn()} />);
    await search(user, "rede neural");
    await user.type(screen.getByRole("textbox", { name: "Replace with" }), "RN");
    await user.click(screen.getByRole("button", { name: "Replace the match in chapters/intro.tex, line 1" }));
    await vi.waitFor(() => expect(texts["chapters/intro.tex"]).toBe("Outra RN aqui.\n"));
    expect(texts["main.tex"]).toBe(SOURCES[0].text);
  });

  it("offers no replace to a viewer", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<Harness sources={SOURCES} onOpen={vi.fn()} />);
    await search(user, "rede");
    expect(screen.queryByRole("textbox", { name: "Replace with" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Replace all" })).toBeNull();
    expect(screen.queryByRole("button", { name: /Replace this match/ })).toBeNull();
    expect(screen.getByText("You can view this project, so replacing is off.")).toBeInTheDocument();
  });
});
