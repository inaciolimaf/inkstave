import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ fetchProposal: vi.fn() }));
vi.mock("./api", () => api);
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

import { proposal, render } from "./test-helpers";

afterEach(() => vi.clearAllMocks());

describe("DiffReviewDialog (CodeMirror preview)", () => {
  it("renders a read-only CodeMirror preview (not a <pre>) when Preview is toggled (#192/AC2)", async () => {
    api.fetchProposal.mockResolvedValue(proposal());
    const { ui } = render();
    await screen.findByText("main.tex");
    await userEvent.click(screen.getByRole("button", { name: "Preview" }));

    const host = await screen.findByTestId("preview-editor");
    expect(host.querySelector(".cm-editor")).toBeTruthy();
    expect(host.querySelector("pre.cm-content, .cm-content")).toBeTruthy();
    // The preview must reflect the accepted result (b -> B, d -> D applied).
    expect(host.textContent).toContain("B");
    // No raw <pre> preview remains.
    expect(ui.container.querySelector("pre.font-mono")).toBeNull();
    // Non-editable: the content region is marked read-only.
    expect(host).toHaveAttribute("aria-readonly", "true");
  });
});
