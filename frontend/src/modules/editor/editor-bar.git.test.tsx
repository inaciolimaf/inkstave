import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { EditorBar } from "./editor-bar";

const flags = vi.hoisted(() => ({ git_enabled: false }));
vi.mock("@/lib/public-config", () => ({ usePublicConfig: () => flags }));
vi.mock("@/modules/notifications", () => ({ NotificationsBell: () => <button>Notifications</button> }));

function renderBar() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <EditorBar
          projectId="p9"
          projectName="Thesis"
          fileName="main.tex"
          onOpenFiles={vi.fn()}
          compileSlotRef={vi.fn()}
          historyDisabled={false}
          onOpenHistory={vi.fn()}
          onOpenShare={vi.fn()}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("EditorBar Git menu (spec 121)", () => {
  beforeEach(() => {
    flags.git_enabled = false;
  });

  it("has no Git item when the server runs without Git", async () => {
    renderBar();
    await userEvent.click(screen.getByRole("button", { name: "More actions" }));
    expect(screen.queryByRole("menuitem", { name: "Git" })).not.toBeInTheDocument();
  });

  it("opens the clone address for this project when Git is on", async () => {
    flags.git_enabled = true;
    renderBar();
    await userEvent.click(screen.getByRole("button", { name: "More actions" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Git" }));
    const dialog = await screen.findByRole("dialog");
    expect(
      within(dialog).getAllByText(/\/api\/v1\/git\/projects\/p9\.git$/, { selector: "code" }),
    ).toHaveLength(2);
  });
});
