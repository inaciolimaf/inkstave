import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AskAgentButton } from "./ask-agent-button";
import { placeAbove } from "./use-editor-selection";

const selection = { text: "x", fromLine: 1, toLine: 1, anchor: { left: 100, top: 200 } };

describe("AskAgentButton", () => {
  it("asks without stealing the editor's focus", async () => {
    const onAsk = vi.fn();
    render(<AskAgentButton selection={selection} floating onAsk={onAsk} />);
    const button = screen.getByRole("button", { name: "Ask the agent" });
    await userEvent.click(button);
    expect(onAsk).toHaveBeenCalledOnce();
    expect(document.activeElement).not.toBe(button);
  });

  it("hides on desktop when the selection scrolled away, and stays on a phone", () => {
    const away = { ...selection, anchor: null };
    const { rerender } = render(<AskAgentButton selection={away} floating onAsk={vi.fn()} />);
    expect(screen.queryByRole("button")).toBeNull();
    rerender(<AskAgentButton selection={away} floating={false} onAsk={vi.fn()} />);
    expect(screen.getByRole("button")).toBeInTheDocument();
  });

  it("stays on screen near the edges", () => {
    expect(placeAbove({ left: 5, top: 10 }, 1000)).toEqual({ left: 8, top: 8 });
    expect(placeAbove({ left: 990, top: 300 }, 1000)).toEqual({ left: 820, top: 256 });
  });
});
