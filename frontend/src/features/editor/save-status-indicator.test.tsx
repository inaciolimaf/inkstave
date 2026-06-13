import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { SaveStatus } from "./autosave/types";
import { SaveStatusIndicator } from "./save-status-indicator";

describe("SaveStatusIndicator", () => {
  it.each<[SaveStatus, string]>([
    ["clean", "Saved"],
    ["dirty", "Unsaved changes"],
    ["saving", "Saving…"],
    ["error", "Save failed — retrying"],
    ["offline", "Offline — changes will save when you reconnect"],
    ["conflict", "Conflict"],
  ])("renders %s as “%s”", (status, label) => {
    render(<SaveStatusIndicator status={status} onRetry={vi.fn()} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it("renders a relative timestamp for the clean state when lastSavedAt is set", () => {
    render(<SaveStatusIndicator status="clean" onRetry={vi.fn()} lastSavedAt={Date.now()} />);
    expect(screen.getByText("Saved just now")).toBeInTheDocument();
  });

  it("renders an older relative phrase for an earlier lastSavedAt", () => {
    render(
      <SaveStatusIndicator status="clean" onRetry={vi.fn()} lastSavedAt={Date.now() - 90_000} />,
    );
    expect(screen.getByText(/Saved \d+m ago/)).toBeInTheDocument();
  });

  it("falls back to the static Saved label when lastSavedAt is null", () => {
    render(<SaveStatusIndicator status="clean" onRetry={vi.fn()} lastSavedAt={null} />);
    expect(screen.getByText("Saved")).toBeInTheDocument();
  });

  it("exposes an aria-live region", () => {
    const { container } = render(<SaveStatusIndicator status="clean" onRetry={vi.fn()} />);
    expect(container.querySelector('[aria-live="polite"]')).toBeTruthy();
  });

  it("offers a Retry action only in the error state", async () => {
    const onRetry = vi.fn();
    const { rerender } = render(<SaveStatusIndicator status="saving" onRetry={onRetry} />);
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();

    rerender(<SaveStatusIndicator status="error" onRetry={onRetry} />);
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalled();
  });
});
