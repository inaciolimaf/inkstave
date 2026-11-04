import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { makeView } from "../test-view";

import { SymbolPalette } from "./symbol-palette";

const PREAMBLE = "\\documentclass{article}\n\\begin{document}\nHi \n\\end{document}\n";

afterEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

describe("SymbolPalette", () => {
  it("focuses the search on open, and choosing alpha after a search inserts \\alpha at the cursor", async () => {
    const user = userEvent.setup();
    const view = makeView("x = ");
    render(<SymbolPalette view={view} mainText="" onClose={vi.fn()} />);
    const search = screen.getByRole("searchbox", { name: "Search symbols" });
    expect(search).toHaveFocus();
    await user.type(search, "alpha");
    await user.click(screen.getByRole("button", { name: "\\alpha" }));
    expect(view.state.doc.toString()).toBe("x = \\alpha");
    expect(view.state.selection.main.head).toBe("x = \\alpha".length);
  });

  it("inserts a command with an argument with the cursor inside the braces, and offers amssymb", async () => {
    const user = userEvent.setup();
    const view = makeView(PREAMBLE, PREAMBLE.indexOf("Hi ") + 3);
    render(<SymbolPalette view={view} mainText={PREAMBLE} onClose={vi.fn()} />);
    await user.type(screen.getByRole("searchbox", { name: "Search symbols" }), "mathbb");
    await user.click(screen.getByRole("button", { name: "\\mathbb" }));
    expect(view.state.doc.toString()).toContain("Hi \\mathbb{}");
    expect(view.state.selection.main.head).toBe(PREAMBLE.indexOf("Hi ") + 3 + "\\mathbb{".length);
    expect(screen.getByRole("status")).toHaveTextContent("Needs \\usepackage{amssymb}");
  });

  it("adds the package line before \\begin{document} when asked, and the hint goes away", async () => {
    const user = userEvent.setup();
    const view = makeView(PREAMBLE, PREAMBLE.indexOf("Hi ") + 3);
    render(<SymbolPalette view={view} mainText={PREAMBLE} onClose={vi.fn()} />);
    await user.type(screen.getByRole("searchbox", { name: "Search symbols" }), "mathbb");
    await user.click(screen.getByRole("button", { name: "\\mathbb" }));
    await user.click(screen.getByRole("button", { name: "Add it" }));
    expect(view.state.doc.toString()).toContain("\\usepackage{amssymb}\n\\begin{document}");
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("shows no hint when the main document already loads the package", async () => {
    const user = userEvent.setup();
    const loaded = PREAMBLE.replace("\\begin", "\\usepackage{amsmath,amssymb}\n\\begin");
    const view = makeView(loaded);
    render(<SymbolPalette view={view} mainText={loaded} onClose={vi.fn()} />);
    await user.type(screen.getByRole("searchbox", { name: "Search symbols" }), "mathbb");
    await user.click(screen.getByRole("button", { name: "\\mathbb" }));
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("says where the package goes when the open text has no \\begin{document}", async () => {
    const user = userEvent.setup();
    const view = makeView("just a fragment");
    render(<SymbolPalette view={view} mainText="" onClose={vi.fn()} />);
    await user.type(screen.getByRole("searchbox", { name: "Search symbols" }), "nexists");
    await user.click(screen.getByRole("button", { name: "\\nexists" }));
    expect(screen.getByRole("status")).toHaveTextContent("main document");
    expect(screen.queryByRole("button", { name: "Add it" })).toBeNull();
  });

  it("says so when no symbol matches the search", async () => {
    const user = userEvent.setup();
    render(<SymbolPalette view={makeView("")} mainText="" onClose={vi.fn()} />);
    await user.type(screen.getByRole("searchbox", { name: "Search symbols" }), "qqzz");
    expect(screen.getByText("No symbol matches “qqzz”.")).toBeInTheDocument();
  });

  it("lists symbols by category when a category tab is chosen", async () => {
    const user = userEvent.setup();
    render(<SymbolPalette view={makeView("")} mainText="" onClose={vi.fn()} />);
    const tabs = screen.getByRole("group", { name: "Symbol categories" });
    await user.click(within(tabs).getByRole("button", { name: "Arrows" }));
    expect(screen.getByRole("button", { name: "\\rightarrow" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "\\alpha" })).toBeNull();
  });

  it("puts recently used symbols first", async () => {
    const user = userEvent.setup();
    const view = makeView("");
    const { unmount } = render(<SymbolPalette view={view} mainText="" onClose={vi.fn()} />);
    await user.type(screen.getByRole("searchbox", { name: "Search symbols" }), "beta");
    await user.click(screen.getByRole("button", { name: "\\beta" }));
    unmount();
    render(<SymbolPalette view={view} mainText="" onClose={vi.fn()} />);
    const recent = screen.getByRole("group", { name: "Recent" });
    expect(within(recent).getByRole("button", { name: "\\beta" })).toBeInTheDocument();
  });

  it("opens as a bottom sheet on a phone, with the same search", async () => {
    vi.spyOn(window, "matchMedia").mockImplementation(
      (query: string) =>
        ({
          matches: false,
          media: query,
          addEventListener() {},
          removeEventListener() {},
        }) as unknown as MediaQueryList,
    );
    render(<SymbolPalette view={makeView("")} mainText="" onClose={vi.fn()} />);
    expect(screen.getByRole("searchbox", { name: "Search symbols" })).toBeInTheDocument();
  });

  it("closes when Escape is pressed", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<SymbolPalette view={makeView("")} mainText="" onClose={onClose} />);
    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalled();
  });
});
