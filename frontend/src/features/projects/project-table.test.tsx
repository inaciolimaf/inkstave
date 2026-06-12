import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { ProjectTable } from "./project-table";
import type { Project } from "./types";

const projects: Project[] = [
  {
    id: "abc",
    name: "Thesis",
    ownerId: "u",
    createdAt: "2026-01-01T00:00:00Z",
    updatedAt: "2026-02-01T00:00:00Z",
  },
];

function setup() {
  const handlers = { onOpen: vi.fn(), onRename: vi.fn(), onDelete: vi.fn() };
  render(
    <MemoryRouter>
      <ProjectTable projects={projects} {...handlers} />
    </MemoryRouter>,
  );
  return handlers;
}

describe("ProjectTable", () => {
  it("links each project name to its editor route", () => {
    setup();
    expect(screen.getByRole("link", { name: "Thesis" })).toHaveAttribute("href", "/projects/abc");
  });

  it("has a visually-hidden caption for screen readers", () => {
    setup();
    expect(screen.getByText("Your projects")).toBeInTheDocument();
  });

  it("exposes Open / Rename / Delete in the row actions menu", async () => {
    const handlers = setup();
    await userEvent.click(screen.getByRole("button", { name: "Project actions" }));

    expect(await screen.findByRole("menuitem", { name: "Open" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Rename" })).toBeInTheDocument();
    const del = screen.getByRole("menuitem", { name: "Delete" });
    expect(del).toBeInTheDocument();

    await userEvent.click(del);
    expect(handlers.onDelete).toHaveBeenCalledWith(projects[0]);
  });
});
