import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { PreviewEmptyState } from "./PreviewEmptyState";
import { PreviewErrorState } from "./PreviewErrorState";

describe("PreviewEmptyState", () => {
  it("invites the user to compile", () => {
    render(<PreviewEmptyState />);
    expect(screen.getByText(/compile to see a preview/i)).toBeInTheDocument();
  });
});

describe("PreviewErrorState", () => {
  it.each([
    ["failure", "Compilation failed"],
    ["timeout", "Compilation timed out"],
    ["error", "Something went wrong"],
  ] as const)("renders the %s outcome title", (outcome, title) => {
    render(<PreviewErrorState outcome={outcome} onViewLog={vi.fn()} onRetry={vi.fn()} />);
    expect(screen.getByRole("alert")).toHaveTextContent(title);
  });

  it("triggers View log and Try again", async () => {
    const onViewLog = vi.fn();
    const onRetry = vi.fn();
    render(<PreviewErrorState outcome="failure" onViewLog={onViewLog} onRetry={onRetry} />);
    await userEvent.click(screen.getByRole("button", { name: "View log" }));
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onViewLog).toHaveBeenCalled();
    expect(onRetry).toHaveBeenCalled();
  });

  it("shows a custom detail message when provided", () => {
    render(
      <PreviewErrorState
        outcome="error"
        detail="disk full"
        onViewLog={vi.fn()}
        onRetry={vi.fn()}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("disk full");
  });
});
