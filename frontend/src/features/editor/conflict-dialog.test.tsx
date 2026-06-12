import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ConflictDialog } from "./conflict-dialog";

describe("ConflictDialog", () => {
  it("offers both resolutions; the non-destructive option holds default focus", async () => {
    render(<ConflictDialog open onOpenChange={vi.fn()} onReload={vi.fn()} onKeepMine={vi.fn()} />);
    expect(screen.getByText(/changed on the server/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reload server version" })).toBeInTheDocument();
    // "Reload" discards local edits, so it must NOT be the default focus.
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Keep my version" })).toHaveFocus(),
    );
  });

  it("invokes the chosen resolution", async () => {
    const onReload = vi.fn();
    const onKeepMine = vi.fn();
    render(
      <ConflictDialog open onOpenChange={vi.fn()} onReload={onReload} onKeepMine={onKeepMine} />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Reload server version" }));
    expect(onReload).toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Keep my version" }));
    expect(onKeepMine).toHaveBeenCalled();
  });
});
