import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { EditorBar } from "./editor-bar";

vi.mock("@/modules/notifications", () => ({ NotificationsBell: () => <button>Notifications</button> }));

function renderBar(projectName: string | undefined) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <EditorBar
          projectId="p"
          projectName={projectName}
          agentOpen={false}
          onToggleAgent={vi.fn()}
          historyDisabled
          onOpenHistory={vi.fn()}
          onOpenShare={vi.fn()}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("EditorBar", () => {
  it("holds the mark, the title, the way back and the tools in one bar, in that order (spec 106)", () => {
    renderBar("Thesis");
    const bar = within(screen.getByRole("banner"));
    const order = [
      bar.getByRole("link", { name: "Inkstave" }),
      bar.getByRole("heading", { level: 1, name: "Thesis" }),
      bar.getByRole("link", { name: "Back to projects" }),
      bar.getByRole("button", { name: "History" }),
      bar.getByRole("button", { name: "Download" }),
      bar.getByRole("button", { name: "Share" }),
      bar.getByRole("button", { name: "Notifications" }),
    ];
    for (const [i, element] of order.slice(1).entries()) {
      expect(order[i]!.compareDocumentPosition(element)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    }
  });

  it("titles the screen while the project loads", () => {
    renderBar(undefined);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Loading");
  });
});
