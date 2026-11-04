import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { ResolvedItem } from "@/modules/project-index";

import { OutlinePanel } from "./outline-panel";

const entries: ResolvedItem[] = [
  { kind: "section", level: 2, title: "Introduction", line: 1, docId: "main", path: "main.tex" },
  { kind: "label", title: "sec:intro", line: 2, docId: "main", path: "main.tex" },
  { kind: "section", level: 2, title: "Background", line: 6, docId: "intro", path: "chapters/intro.tex" },
  { kind: "section", level: 3, title: "History", line: 10, docId: "intro", path: "chapters/intro.tex" },
  { kind: "section", level: 2, title: "Method", line: 20, docId: "main", path: "main.tex" },
];

function renderPanel(overrides: Partial<Parameters<typeof OutlinePanel>[0]> = {}) {
  const onOpen = vi.fn();
  const props = {
    entries,
    status: "ready" as const,
    openDocId: "main",
    cursorLine: 1,
    onOpen,
    ...overrides,
  };
  render(<OutlinePanel {...props} />);
  return { onOpen };
}

describe("OutlinePanel", () => {
  it("lists the sections in order and leaves the labels out", () => {
    renderPanel();
    const rows = screen.getAllByRole("treeitem");
    expect(rows.map((row) => row.querySelector("span")?.textContent)).toEqual([
      "Introduction",
      "Background",
      "History",
      "Method",
    ]);
  });

  it("names the file of the entries from other files, and no others", () => {
    renderPanel();
    const background = screen.getByText("Background").closest("li") as HTMLElement;
    expect(within(background).getByText("intro.tex")).toBeInTheDocument();
    const intro = screen.getByText("Introduction").closest("li") as HTMLElement;
    expect(within(intro).queryByText("main.tex")).toBeNull();
  });

  it("marks the section that holds the cursor for assistive tech", () => {
    renderPanel({ cursorLine: 12, openDocId: "intro" });
    const history = screen.getByText("History").closest("li");
    expect(history).toHaveAttribute("aria-current", "location");
    expect(screen.getAllByRole("treeitem").filter((row) => row.hasAttribute("aria-current"))).toHaveLength(1);
  });

  it("opens an entry on click", async () => {
    const { onOpen } = renderPanel();
    await userEvent.click(screen.getByText("Method"));
    expect(onOpen).toHaveBeenCalledWith(entries[4]);
  });

  it("moves with the arrow keys and opens with Enter", async () => {
    const { onOpen } = renderPanel();
    screen.getByText("Introduction").closest("li")!.focus();
    await userEvent.keyboard("{ArrowDown}{ArrowDown}");
    expect(screen.getByText("History").closest("li")).toHaveFocus();
    await userEvent.keyboard("{End}");
    expect(screen.getByText("Method").closest("li")).toHaveFocus();
    await userEvent.keyboard("{Home}{Enter}");
    expect(onOpen).toHaveBeenCalledWith(entries[0]);
  });

  it("shows the empty state with the code in monospace", () => {
    renderPanel({ entries: [] });
    const hint = screen.getByText(/No sections yet/);
    expect(hint.querySelector("code")).toHaveTextContent("\\section{…}");
    expect(screen.queryByRole("tree")).toBeNull();
  });

  it("says when only the open file is shown", () => {
    renderPanel({ status: "limited" });
    expect(screen.getByRole("status")).toHaveTextContent(/too large/);
  });

  it("offers the pin toggle only where the outline can be pinned", async () => {
    const onToggle = vi.fn();
    renderPanel({ pin: { pinned: false, onToggle } });
    await userEvent.click(screen.getByRole("button", { name: "Pin the outline beside the text" }));
    expect(onToggle).toHaveBeenCalledTimes(1);
  });
});
