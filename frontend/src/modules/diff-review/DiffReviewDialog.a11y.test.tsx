import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ fetchProposal: vi.fn() }));
vi.mock("./api", () => api);
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

import { proposal, render } from "./test-helpers";

afterEach(() => vi.clearAllMocks());

describe("DiffReviewDialog (accessibility)", () => {
  it("conveys add/remove non-visually and keeps toggles keyboard-operable (AC11)", async () => {
    api.fetchProposal.mockResolvedValue(proposal());
    render();
    await screen.findByText("main.tex");

    // (1) sr-only "added:"/"removed:" labels exist for added/removed lines.
    expect(screen.getAllByText("added:").length).toBeGreaterThan(0);
    expect(screen.getAllByText("removed:").length).toBeGreaterThan(0);

    // (2) a hunk toggle is operable via the keyboard (focus + Space toggles it).
    const toggle = screen.getByLabelText("Accept change: @@ -2 @@");
    expect(toggle).toHaveAttribute("aria-checked", "true");
    toggle.focus();
    expect(toggle).toHaveFocus();
    await userEvent.keyboard(" ");
    expect(toggle).toHaveAttribute("aria-checked", "false");
    expect(await screen.findByText("1/2 accepted")).toBeInTheDocument();

    // (3) the apply confirmation dialog traps focus (Tab keeps focus inside it).
    await userEvent.click(screen.getByRole("button", { name: "Apply" }));
    const confirm = await screen.findByRole("alertdialog");
    await userEvent.tab();
    expect(confirm).toContainElement(document.activeElement as HTMLElement);
    await userEvent.tab();
    expect(confirm).toContainElement(document.activeElement as HTMLElement);
  });
});
