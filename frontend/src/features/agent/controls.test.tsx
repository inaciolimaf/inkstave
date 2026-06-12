import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AgentComposer, AgentErrorState, RunControls } from "./controls";

describe("AgentComposer", () => {
  function setup(disabled = false) {
    const onSend = vi.fn();
    const onChange = vi.fn();
    const ui = render(
      <AgentComposer value="hello" onChange={onChange} onSend={onSend} disabled={disabled} />,
    );
    return { onSend, onChange, ui };
  }

  it("sends on Enter, not on Shift+Enter (AC3)", async () => {
    const { onSend } = setup();
    const box = screen.getByLabelText("Message the agent");
    await userEvent.type(box, "{Shift>}{Enter}{/Shift}");
    expect(onSend).not.toHaveBeenCalled();
    await userEvent.type(box, "{Enter}");
    expect(onSend).toHaveBeenCalledWith("hello");
  });

  it("blocks empty/whitespace and disables while streaming", async () => {
    const onSend = vi.fn();
    render(<AgentComposer value="   " onChange={vi.fn()} onSend={onSend} disabled={false} />);
    await userEvent.type(screen.getByLabelText("Message the agent"), "{Enter}");
    expect(onSend).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Send message")).toBeDisabled();

    render(<AgentComposer value="x" onChange={vi.fn()} onSend={vi.fn()} disabled />);
    expect(screen.getAllByLabelText("Message the agent")[1]).toBeDisabled();
  });
});

describe("RunControls", () => {
  it("calls onStop when Stop is clicked (AC7)", async () => {
    const onStop = vi.fn();
    render(<RunControls onStop={onStop} />);
    await userEvent.click(screen.getByRole("button", { name: "Stop the run" }));
    expect(onStop).toHaveBeenCalled();
  });
});

describe("AgentErrorState", () => {
  it("shows Retry only when retryable (AC8)", async () => {
    const onRetry = vi.fn();
    const { rerender } = render(
      <AgentErrorState
        error={{ code: "internal", message: "boom", retryable: true }}
        onRetry={onRetry}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalled();

    rerender(
      <AgentErrorState
        error={{ code: "budget_exceeded", message: "no budget", retryable: false }}
        onRetry={onRetry}
      />,
    );
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
  });
});
