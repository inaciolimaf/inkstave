import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/utils";

import { ProjectIndex } from "./project-index";
import type { ListedProject, ProjectRole } from "./types";

function project(role: ProjectRole): ListedProject {
  return {
    id: "p1",
    name: "Thesis",
    ownerId: "ann",
    rootDocId: null,
    createdAt: "2026-01-01T00:00:00Z",
    updatedAt: "2026-02-01T00:00:00Z",
    role,
    owner: { id: "ann", displayName: "Ann" },
  };
}

function setup(role: ProjectRole) {
  const handlers = { onOpen: vi.fn(), onRename: vi.fn(), onDelete: vi.fn(), onLeave: vi.fn() };
  renderWithProviders(<ProjectIndex projects={[project(role)]} {...handlers} />);
  return handlers;
}

async function openMenu() {
  await userEvent.click(screen.getByRole("button", { name: "Project actions" }));
}

describe("RowActionsMenu by role", () => {
  it("gives the owner rename and delete, but no leave", async () => {
    setup("owner");
    await openMenu();
    expect(await screen.findByRole("menuitem", { name: "Rename" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Delete" })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "Leave project" })).not.toBeInTheDocument();
  });

  it.each(["editor", "viewer"] as const)(
    "gives a %s download and leave, but no rename or delete",
    async (role) => {
      setup(role);
      await openMenu();
      expect(await screen.findByRole("menuitem", { name: "Download as .zip" })).toBeInTheDocument();
      expect(screen.getByRole("menuitem", { name: "Leave project" })).toBeInTheDocument();
      expect(screen.queryByRole("menuitem", { name: "Rename" })).not.toBeInTheDocument();
      expect(screen.queryByRole("menuitem", { name: "Delete" })).not.toBeInTheDocument();
    },
  );

  it("hands the project to onLeave when a non-owner picks Leave project", async () => {
    const handlers = setup("editor");
    await openMenu();
    await userEvent.click(await screen.findByRole("menuitem", { name: "Leave project" }));
    expect(handlers.onLeave).toHaveBeenCalledWith(project("editor"));
    expect(handlers.onDelete).not.toHaveBeenCalled();
  });
});

describe("owner column", () => {
  it("says You for the caller's own project", () => {
    setup("owner");
    expect(screen.getByText("You")).toBeInTheDocument();
    expect(screen.queryByText("Can edit")).not.toBeInTheDocument();
  });

  it("names the owner and marks the caller's role for a shared project", () => {
    setup("editor");
    expect(screen.getByText("Ann")).toBeInTheDocument();
    expect(screen.getByText("Can edit")).toBeInTheDocument();
  });

  it("marks a viewer as can view", () => {
    setup("viewer");
    expect(screen.getByText("Can view")).toBeInTheDocument();
  });
});
