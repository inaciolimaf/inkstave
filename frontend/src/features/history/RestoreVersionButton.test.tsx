import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RestoreVersionButton } from "./RestoreVersionButton";

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

afterEach(() => vi.clearAllMocks());

type Opts = { onSuccess?: (r: { newVersion: number }) => void; onError?: () => void };

function mutation(behaviour: "success" | "error") {
  const mutate = vi.fn((_vars: { version: number; labelName?: string }, opts: Opts) => {
    if (behaviour === "success") opts.onSuccess?.({ newVersion: 9 });
    else opts.onError?.();
  });
  return { mutate, isPending: false } as never;
}

describe("RestoreVersionButton", () => {
  it("opens a confirm dialog explaining the non-destructive restore (AC7)", async () => {
    render(<RestoreVersionButton version={3} restore={mutation("success")} />);
    await userEvent.click(screen.getByRole("button", { name: "Restore this version" }));
    expect(await screen.findByText("Restore version 3?")).toBeInTheDocument();
    expect(screen.getByText(/A new version is created — nothing is deleted/)).toBeInTheDocument();
  });

  it("on confirm calls restore and toasts success (AC8)", async () => {
    const restore = mutation("success");
    render(<RestoreVersionButton version={3} restore={restore} />);
    await userEvent.click(screen.getByRole("button", { name: "Restore this version" }));
    await screen.findByText("Restore version 3?");
    await userEvent.click(screen.getByRole("button", { name: "Restore" }));
    await waitFor(() =>
      expect(
        (restore as unknown as { mutate: ReturnType<typeof vi.fn> }).mutate,
      ).toHaveBeenCalled(),
    );
    expect(toast.success).toHaveBeenCalledWith("Restored to version 3; created version 9.");
  });

  it("on failure surfaces an error and keeps no optimistic change (AC9)", async () => {
    render(<RestoreVersionButton version={3} restore={mutation("error")} />);
    await userEvent.click(screen.getByRole("button", { name: "Restore this version" }));
    await screen.findByText("Restore version 3?");
    await userEvent.click(screen.getByRole("button", { name: "Restore" }));
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    // The dialog stays open after a failure.
    expect(screen.getByText("Restore version 3?")).toBeInTheDocument();
  });
});
