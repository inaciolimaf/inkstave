import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ fetchProposal: vi.fn() }));
vi.mock("./api", () => api);
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

import { createYDocBridge } from "./crdt-apply";
import { proposal, render } from "./test-helpers";

afterEach(() => vi.clearAllMocks());

describe("DiffReviewDialog (apply flow)", () => {
  it("gates apply behind confirm, then writes only accepted hunks (AC4, AC5, AC8)", async () => {
    api.fetchProposal.mockResolvedValue(proposal());
    const { bridge } = render();
    await screen.findByText("main.tex");

    // Reject the second hunk (d -> D).
    await userEvent.click(screen.getByLabelText("Accept change: @@ -4 @@"));
    await userEvent.click(screen.getByRole("button", { name: "Apply" }));

    // Confirm dialog shown; nothing written yet.
    const confirm = await screen.findByRole("alertdialog");
    expect(within(confirm).getByText("Apply changes?")).toBeInTheDocument();
    expect(bridge.getText("main.tex").toString()).toBe("a\nb\nc\nd\n");

    await userEvent.click(within(confirm).getByRole("button", { name: "Apply" }));
    await waitFor(() => expect(bridge.getText("main.tex").toString()).toBe("a\nB\nc\nd\n"));
    expect(await screen.findByText("Changes applied")).toBeInTheDocument();
  });

  it("warns and blocks hunks when the live doc diverged from the proposal (AC7)", async () => {
    api.fetchProposal.mockResolvedValue(proposal());
    // Live doc diverged: line 2 "b" (hunk h1's old context) is now "X", so h1 no
    // longer applies; line 4 "d" (h2's context) is intact.
    const bridge = createYDocBridge({ "main.tex": "a\nX\nc\nd\n" });
    render(bridge);
    await screen.findByText("main.tex");

    // (a) the base-changed banner is shown.
    expect(await screen.findByText("This file changed since the proposal")).toBeInTheDocument();

    // (b) the blocked hunk's switch is disabled; the intact hunk's is not.
    expect(screen.getByLabelText("Accept change: @@ -2 @@")).toBeDisabled();
    expect(screen.getByLabelText("Accept change: @@ -4 @@")).not.toBeDisabled();
    expect(screen.getByText("No longer applies")).toBeInTheDocument();

    // (c) the blocked hunk is excluded from apply (only h2's "d -> D" is written).
    await userEvent.click(screen.getByRole("button", { name: "Apply" }));
    const confirm = await screen.findByRole("alertdialog");
    await userEvent.click(within(confirm).getByRole("button", { name: "Apply" }));
    await waitFor(() => expect(bridge.getText("main.tex").toString()).toBe("a\nX\nc\nD\n"));
  });
});
