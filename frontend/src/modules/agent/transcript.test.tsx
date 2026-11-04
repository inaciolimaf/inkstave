import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AgentTranscript } from "./transcript";
import type { TranscriptItem } from "./types";

function renderItems(items: TranscriptItem[], onReview = vi.fn()) {
  return render(<AgentTranscript items={items} loading={false} onReviewProposal={onReview} />);
}

/**
 * jsdom has no real layout, so the scroll metrics the component reads
 * (`scrollHeight`, `scrollTop`, `clientHeight`) are all 0. Stub them on the
 * scroll container so the pinned/"Jump to latest" logic is exercised
 * deterministically. `clientHeight` is read-only in jsdom, so we redefine it;
 * `scrollTop` is writable, so we just seed it and let the component set it.
 */
function stubScrollMetrics(
  el: HTMLElement,
  {
    scrollHeight,
    clientHeight,
  }: {
    scrollHeight: number;
    clientHeight: number;
  },
) {
  Object.defineProperty(el, "scrollHeight", { configurable: true, value: scrollHeight });
  Object.defineProperty(el, "clientHeight", { configurable: true, value: clientHeight });
}

it("tells the writer's messages from the agent's, in words", () => {
  renderItems([
    { kind: "message", id: "1", role: "user", text: "Hi", status: "complete" },
    { kind: "message", id: "2", role: "assistant", text: "Hello", status: "complete" },
  ]);
  expect(screen.getByText("You")).toBeInTheDocument();
  expect(screen.getByText("Agent")).toBeInTheDocument();
});

describe("AgentTranscript rendering", () => {
  it("sanitizes assistant content (no script execution) (AC10)", () => {
    const { container } = renderItems([
      {
        kind: "message",
        id: "a1",
        role: "assistant",
        text: "<script>alert('xss')</script><img src=x onerror=alert(1)>",
        status: "complete",
      },
    ]);
    // Rendered as inert text, not live HTML (in the bubble + the sr-only announcer).
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getAllByText(/<script>alert/).length).toBeGreaterThan(0);
  });

  it("shows a streaming caret only while streaming", () => {
    const { rerender } = renderItems([
      { kind: "message", id: "a1", role: "assistant", text: "Hi", status: "streaming" },
    ]);
    expect(screen.getByText("▋")).toBeInTheDocument();
    rerender(
      <AgentTranscript
        items={[{ kind: "message", id: "a1", role: "assistant", text: "Hi", status: "complete" }]}
        loading={false}
        onReviewProposal={vi.fn()}
      />,
    );
    expect(screen.queryByText("▋")).toBeNull();
  });

  it("DiffProposalCard calls onReviewProposal with the proposal id (AC6)", async () => {
    const onReview = vi.fn();
    renderItems(
      [
        {
          kind: "diff-proposal",
          id: "d1",
          proposalId: "prop-123",
          status: "proposed",
          files: [{ path: "main.tex", hunkCount: 2 }],
        },
      ],
      onReview,
    );
    expect(screen.getByText(/main\.tex · 2 hunks/)).toBeInTheDocument();
    const review = screen.getByRole("button", { name: /Review changes/ });
    // The composer's send button is the sheet's one solid action (spec 106).
    expect(review).not.toHaveClass("bg-primary");
    await userEvent.click(review);
    expect(onReview).toHaveBeenCalledWith("prop-123", "main.tex");
  });

  it("shows a decided proposal as decided, with no review to open (spec 110)", () => {
    const items: TranscriptItem[] = [
      {
        kind: "diff-proposal",
        id: "d1",
        proposalId: "prop-9",
        status: "partially_applied",
        files: [{ path: "main.tex", hunkCount: 3 }],
      },
    ];
    render(
      <AgentTranscript
        items={items}
        loading={false}
        onReviewProposal={vi.fn()}
        proposalStatuses={{ "prop-9": "applied" }}
      />,
    );
    expect(screen.queryByRole("button", { name: /Review changes/ })).not.toBeInTheDocument();
    expect(screen.getByText("Applied")).toBeInTheDocument();
  });

  it("shows the outcome of a proposal from the stored status when no decision came in this page", () => {
    renderItems([
      {
        kind: "diff-proposal",
        id: "d2",
        proposalId: "prop-10",
        status: "rejected",
        files: [{ path: "a.tex", hunkCount: 1 }],
      },
    ]);
    expect(screen.getByText("Rejected")).toBeInTheDocument();
  });

  it("folds neighbouring tool calls into one line that opens in plain words (spec 107)", async () => {
    renderItems([
      { kind: "tool", id: "c1", name: "read_file", args: { path: "main.tex" }, result: "ok", status: "ok" },
      { kind: "tool", id: "c2", name: "search_project", args: { query: "cite" }, result: "ok", status: "ok" },
    ]);
    const row = screen.getByRole("button", { name: /2 steps/ });
    expect(row).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(row);
    expect(row).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("main.tex")).toBeInTheDocument();
    expect(screen.getByText("cite")).toBeInTheDocument();
    expect(screen.queryByText(/"path"/)).toBeNull();
  });

  it("names the running step while the agent works", () => {
    renderItems([
      { kind: "tool", id: "c1", name: "read_file", args: {}, result: "ok", status: "ok" },
      { kind: "tool", id: "c2", name: "search_project", args: {}, status: "running" },
    ]);
    expect(screen.getByRole("button", { name: /Searched the project/ })).toBeInTheDocument();
  });

  it("stays pinned to the bottom as new items arrive, hiding 'Jump to latest' (AC autoscroll)", () => {
    const initial: TranscriptItem[] = [
      { kind: "message", id: "u1", role: "user", text: "hi", status: "complete" },
    ];
    const { rerender } = renderItems(initial);
    const log = screen.getByRole("log", { name: "Conversation" });
    stubScrollMetrics(log, { scrollHeight: 1000, clientHeight: 400 });

    // A new item arrives while pinned → the effect scrolls to the bottom.
    rerender(
      <AgentTranscript
        items={[
          ...initial,
          { kind: "message", id: "a1", role: "assistant", text: "reply", status: "complete" },
        ]}
        loading={false}
        onReviewProposal={vi.fn()}
      />,
    );
    expect(log.scrollTop).toBe(1000); // pinned to bottom (scrollTop := scrollHeight)
    expect(screen.queryByRole("button", { name: /Jump to latest/ })).toBeNull();
  });

  it("shows 'Jump to latest' after scrolling up and re-pins on click (AC autoscroll)", () => {
    renderItems([
      { kind: "message", id: "u1", role: "user", text: "hi", status: "complete" },
      { kind: "message", id: "a1", role: "assistant", text: "reply", status: "complete" },
    ]);
    const log = screen.getByRole("log", { name: "Conversation" });
    stubScrollMetrics(log, { scrollHeight: 1000, clientHeight: 400 });

    // Scroll well up from the bottom (gap = 1000 - 100 - 400 = 500 ≥ 48) → unpin.
    log.scrollTop = 100;
    fireEvent.scroll(log);
    expect(screen.getByRole("button", { name: /Jump to latest/ })).toBeInTheDocument();

    // Clicking re-pins: the effect runs and scrolls back to the bottom; control hides.
    fireEvent.click(screen.getByRole("button", { name: /Jump to latest/ }));
    expect(log.scrollTop).toBe(1000);
    expect(screen.queryByRole("button", { name: /Jump to latest/ })).toBeNull();
  });

  it("has a labelled log plus a polite announcer that only carries completed text (AC10)", () => {
    renderItems([
      { kind: "message", id: "u1", role: "user", text: "hi", status: "complete" },
      { kind: "message", id: "a1", role: "assistant", text: "streaming…", status: "streaming" },
    ]);
    // The log region is no longer a live region (per-token flooding fix, spec 50)…
    const log = screen.getByRole("log", { name: "Conversation" });
    expect(log).not.toHaveAttribute("aria-live");
    // …a dedicated status node announces completed content only (not the streaming msg).
    const announcer = screen.getByRole("status");
    expect(announcer).toHaveAttribute("aria-live", "polite");
    expect(announcer).not.toHaveTextContent("streaming…");
  });
});
