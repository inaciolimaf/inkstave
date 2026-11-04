/** The Suggestions tab: the rows, the decisions of a writer, and none for a viewer (spec 119 §9). */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { SuggestionsTab, type SuggestionRow, type SuggestionsTabProps } from "./suggestions-tab";

const ROWS: SuggestionRow[] = [
  {
    id: "s1",
    kind: "insert",
    authorName: "Bia",
    createdAt: "2026-11-04T10:00:00Z",
    text: "very ",
    stale: false,
  },
  {
    id: "s2",
    kind: "delete",
    authorName: "Caio",
    createdAt: "2026-11-04T10:01:00Z",
    text: "old ",
    stale: false,
  },
  { id: "s3", kind: "insert", authorName: "Dani", createdAt: "2026-11-04T10:02:00Z", text: "", stale: true },
];

function props(over: Partial<SuggestionsTabProps> = {}): SuggestionsTabProps {
  return { rows: ROWS, canDecide: true, onDecide: vi.fn(), onDecideAll: vi.fn(), ...over };
}

function rows(): HTMLElement[] {
  return screen.getAllByRole("article");
}

describe("SuggestionsTab", () => {
  it("lists every suggestion in the order given, with its author and text", () => {
    render(<SuggestionsTab {...props()} />);
    const items = rows();
    expect(items).toHaveLength(3);
    expect(items[0]).toHaveTextContent("very");
    expect(items[1]).toHaveTextContent("old");
    expect(screen.getByRole("article", { name: "Deletion by Caio" })).toBeInTheDocument();
  });

  it("accepts and rejects one suggestion, and decides the whole document", async () => {
    const user = userEvent.setup();
    const p = props();
    render(<SuggestionsTab {...p} />);
    const first = rows()[0];
    await user.click(within(first).getByRole("button", { name: "Accept" }));
    expect(p.onDecide).toHaveBeenLastCalledWith("s1", "accept");
    await user.click(within(first).getByRole("button", { name: "Reject" }));
    expect(p.onDecide).toHaveBeenLastCalledWith("s1", "reject");
    await user.click(screen.getByRole("button", { name: "Accept all" }));
    expect(p.onDecideAll).toHaveBeenLastCalledWith("accept");
    await user.click(screen.getByRole("button", { name: "Reject all" }));
    expect(p.onDecideAll).toHaveBeenLastCalledWith("reject");
  });

  it("shows a stale suggestion as no longer applying, with only Dismiss", async () => {
    const user = userEvent.setup();
    const p = props();
    render(<SuggestionsTab {...p} />);
    const stale = rows()[2];
    expect(stale).toHaveTextContent("No longer applies");
    expect(within(stale).queryByRole("button", { name: "Accept" })).toBeNull();
    await user.click(within(stale).getByRole("button", { name: "Dismiss" }));
    expect(p.onDecide).toHaveBeenLastCalledWith("s3", "dismiss");
  });

  it("a viewer reads the suggestions without any decision", () => {
    render(<SuggestionsTab {...props({ canDecide: false })} />);
    expect(rows()).toHaveLength(3);
    expect(screen.queryByRole("button", { name: "Accept" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Reject" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Accept all" })).toBeNull();
  });

  it("says when there is nothing to show", () => {
    render(<SuggestionsTab {...props({ rows: [] })} />);
    expect(screen.getByText("No suggestions in this document.")).toBeInTheDocument();
  });
});
