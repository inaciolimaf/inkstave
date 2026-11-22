import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { installLivedInFetch, LIVED } from "@/test/lived-in";
import { renderWithProviders } from "@/test/utils";

import { AgentPanel } from "./AgentPanel";

class QuietEventSource {
  onerror: (() => void) | null = null;
  addEventListener() {}
  close() {}
}

beforeEach(() => vi.stubGlobal("EventSource", QuietEventSource));
afterEach(() => vi.unstubAllGlobals());

function renderPanel() {
  return renderWithProviders(
    <AgentPanel projectId={LIVED.projectId} open onOpenChange={vi.fn()} onReviewProposal={vi.fn()} />,
  );
}

describe("AgentPanel on a lived-in project", () => {
  it("reopens an existing chat with its earlier turn and the proposal waiting for review", async () => {
    installLivedInFetch();
    renderPanel();

    await userEvent.click(await screen.findByRole("button", { name: "Sessions" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Polish" }));

    expect(await screen.findByText("Tighten the introduction.")).toBeInTheDocument();
    expect(screen.getAllByText("Here is a tighter version.").length).toBeGreaterThan(0);
    expect(screen.getByText("chapters/intro.tex · 1 hunk")).toBeInTheDocument();
  });

  it("does not create a chat on its own when the project already has one", async () => {
    const fetchMock = installLivedInFetch();
    renderPanel();
    await screen.findByRole("button", { name: "Sessions" });

    const posts = fetchMock.mock.calls.filter(
      ([, init]) => (init as RequestInit | undefined)?.method === "POST",
    );
    expect(posts).toHaveLength(0);
  });
});
