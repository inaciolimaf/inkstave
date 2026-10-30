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
          files: [{ path: "main.tex", hunkCount: 2 }],
        },
      ],
      onReview,
    );
    expect(screen.getByText(/main\.tex · 2 hunks/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Review changes/ }));
    expect(onReview).toHaveBeenCalledWith("prop-123");
  });

  it("ToolActivityRow expands to show args/result (AC5)", async () => {
    renderItems([
      {
        kind: "tool",
        id: "c1",
        name: "read_file",
        args: { doc_id: "x" },
        result: "ok",
        status: "ok",
      },
    ]);
    const row = screen.getByRole("button", { name: /Read a file/ });
    expect(row).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(row);
    expect(row).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(/"doc_id": "x"/)).toBeInTheDocument();
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
