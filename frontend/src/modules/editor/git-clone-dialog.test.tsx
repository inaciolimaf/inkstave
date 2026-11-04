import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { config } from "@/config";

import { GitCloneDialog } from "./git-clone-dialog";
import { gitCloneUrl } from "./git-url";

describe("GitCloneDialog", () => {
  it("shows the clone address and the clone command for the project (spec 121)", () => {
    const url = gitCloneUrl("p1");
    expect(url).toBe(`${config.apiBaseUrl}/api/v1/git/projects/p1.git`);
    render(
      <MemoryRouter>
        <GitCloneDialog projectId="p1" open onOpenChange={vi.fn()} />
      </MemoryRouter>,
    );
    expect(screen.getByText(url)).toBeInTheDocument();
    expect(screen.getByText(`git clone ${url}`)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Manage tokens" })).toHaveAttribute("href", "/settings");
  });

  it("closes through its close button", async () => {
    const onOpenChange = vi.fn();
    render(
      <MemoryRouter>
        <GitCloneDialog projectId="p1" open onOpenChange={onOpenChange} />
      </MemoryRouter>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
