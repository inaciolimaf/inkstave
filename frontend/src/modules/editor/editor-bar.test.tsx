import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { EditorBar } from "./editor-bar";

vi.mock("@/modules/notifications", () => ({ NotificationsBell: () => <button>Notifications</button> }));

function renderBar(projectName: string | undefined, onOpenFiles = vi.fn()) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <EditorBar
          projectId="p"
          projectName={projectName}
          fileName="main.tex"
          onOpenFiles={onOpenFiles}
          compileSlotRef={vi.fn()}
          historyDisabled
          onOpenHistory={vi.fn()}
          onOpenShare={vi.fn()}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("EditorBar", () => {
  it("holds the mark, the title, the open file and the tools in one bar, in that order (spec 107)", () => {
    renderBar("Thesis");
    const bar = within(screen.getByRole("banner"));
    const order = [
      bar.getByRole("link", { name: "Inkstave" }),
      bar.getByRole("heading", { level: 1, name: "Thesis" }),
      bar.getByRole("button", { name: "Switch file (main.tex)" }),
      bar.getByRole("button", { name: "Share" }),
      bar.getByRole("button", { name: "Notifications" }),
      bar.getByRole("button", { name: "More actions" }),
    ];
    for (const [i, element] of order.slice(1).entries()) {
      expect(order[i]!.compareDocumentPosition(element)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    }
  });

  it("opens the file list from the name of the open file", async () => {
    const onOpenFiles = vi.fn();
    renderBar("Thesis", onOpenFiles);
    await userEvent.click(screen.getByRole("button", { name: "Switch file (main.tex)" }));
    expect(onOpenFiles).toHaveBeenCalledOnce();
  });

  it("keeps history, download and the way back in the menu", async () => {
    renderBar("Thesis");
    await userEvent.click(screen.getByRole("button", { name: "More actions" }));
    expect(screen.getByRole("menuitem", { name: "History" })).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByRole("menuitem", { name: "Download" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Back to projects" })).toHaveAttribute("href", "/projects");
  });

  it("titles the screen while the project loads", () => {
    renderBar(undefined);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Loading");
  });
});
