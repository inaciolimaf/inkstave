import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ fetchProposal: vi.fn() }));
vi.mock("./api", () => api);
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

import { proposal, render } from "./test-helpers";

afterEach(() => vi.clearAllMocks());

describe("DiffReviewDialog (accept/reject)", () => {
  it("toggling a hunk updates the accepted counter (AC2)", async () => {
    api.fetchProposal.mockResolvedValue(proposal());
    render();
    await screen.findByText("main.tex");
    await userEvent.click(screen.getByLabelText("Accept change: @@ -4 @@"));
    expect(await screen.findByText("1/2 accepted")).toBeInTheDocument();
  });

  it("Accept all / Reject all toggle the accepted count and the apply plan (#AC4)", async () => {
    api.fetchProposal.mockResolvedValue(proposal());
    const { bridge, ui } = render();
    await screen.findByText("main.tex");
    expect(screen.getByText("2/2 accepted")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Reject all" }));
    expect(await screen.findByText("0/2 accepted")).toBeInTheDocument();

    // With nothing accepted, applying writes nothing.
    await userEvent.click(screen.getByRole("button", { name: "Apply" }));
    const confirm = await screen.findByRole("alertdialog");
    await userEvent.click(within(confirm).getByRole("button", { name: "Apply" }));
    await screen.findByText("Changes applied");
    expect(bridge.getText("main.tex").toString()).toBe("a\nb\nc\nd\n");

    // Re-open a fresh dialog and Accept all -> all hunks apply. Unmount the first
    // so its (now stale) counter/labels don't collide with the second dialog.
    ui.unmount();
    api.fetchProposal.mockResolvedValue(proposal());
    const second = render();
    await screen.findByText("main.tex");
    await userEvent.click(screen.getByRole("button", { name: "Reject all" }));
    await screen.findByText("0/2 accepted");
    await userEvent.click(screen.getByRole("button", { name: "Accept all" }));
    expect(await screen.findByText("2/2 accepted")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Apply" }));
    const confirm2 = await screen.findByRole("alertdialog");
    await userEvent.click(within(confirm2).getByRole("button", { name: "Apply" }));
    await waitFor(() => expect(second.bridge.getText("main.tex").toString()).toBe("a\nB\nc\nD\n"));
  });

  it("reject-all then accept-all flips every switch and the counter/preview (AC3)", async () => {
    api.fetchProposal.mockResolvedValue(proposal());
    render();
    await screen.findByText("main.tex");

    // Both hunk switches start accepted.
    expect(screen.getByText("2/2 accepted")).toBeInTheDocument();
    let switches = screen.getAllByRole("switch");
    expect(switches.map((s) => s.getAttribute("aria-checked"))).toEqual(["true", "true"]);

    // Reject all -> every switch flips off and the counter reads 0/2.
    await userEvent.click(screen.getByRole("button", { name: "Reject all" }));
    expect(await screen.findByText("0/2 accepted")).toBeInTheDocument();
    switches = screen.getAllByRole("switch");
    expect(switches.map((s) => s.getAttribute("aria-checked"))).toEqual(["false", "false"]);
    // Preview reflects no accepted hunks: live content is unchanged (no B/D).
    await userEvent.click(screen.getByRole("button", { name: "Preview" }));
    let host = await screen.findByTestId("preview-editor");
    expect(host.textContent).not.toContain("B");
    expect(host.textContent).not.toContain("D");
    await userEvent.click(screen.getByRole("button", { name: "Diff" }));

    // Accept all -> every switch flips on again and the counter reads 2/2.
    await userEvent.click(screen.getByRole("button", { name: "Accept all" }));
    expect(await screen.findByText("2/2 accepted")).toBeInTheDocument();
    switches = screen.getAllByRole("switch");
    expect(switches.map((s) => s.getAttribute("aria-checked"))).toEqual(["true", "true"]);
    // Preview now reflects both accepted hunks (b -> B, d -> D).
    await userEvent.click(screen.getByRole("button", { name: "Preview" }));
    host = await screen.findByTestId("preview-editor");
    expect(host.textContent).toContain("B");
    expect(host.textContent).toContain("D");
  });
});
