import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { installLivedInFetch, LIVED } from "@/test/lived-in";
import { renderWithProviders } from "@/test/utils";

import { HistoryPanel } from "./HistoryPanel";

afterEach(() => vi.unstubAllGlobals());

function renderHistory(docId: string) {
  return renderWithProviders(
    <HistoryPanel projectId={LIVED.projectId} docId={docId} open onOpenChange={vi.fn()} />,
  );
}

describe("HistoryPanel on a lived-in project", () => {
  it("lists the versions recorded for main.tex, newest first", async () => {
    installLivedInFetch();
    renderHistory(LIVED.ids.main);

    const list = await screen.findByRole("list", { name: "Version history" });
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    const text = items.map((item) => item.textContent ?? "").join("|");
    expect(text).toContain("v1");
    expect(text).toContain("v2");
  });

  it("shows what a selected version changed against the current text", async () => {
    const fetchMock = installLivedInFetch();
    renderHistory(LIVED.ids.main);
    await userEvent.click(await screen.findByText(/^v1/));

    expect(await screen.findByText("\\input{chapters/intro}")).toBeInTheDocument();
    const diffCall = fetchMock.mock.calls
      .map(([url]) => String(url))
      .find((u) => u.includes("/history/diff"));
    expect(diffCall).toContain("from=1");
  });

  it("says there is no history yet for an older document that predates history", async () => {
    installLivedInFetch();
    renderHistory(LIVED.ids.appendix);

    expect(await screen.findByText("No history yet.")).toBeInTheDocument();
  });
});
