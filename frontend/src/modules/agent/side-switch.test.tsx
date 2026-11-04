import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/utils";

import { SideSwitch } from "./panel-parts";

describe("SideSwitch", () => {
  it("shows the Agent | Chat choice with the current view pressed", async () => {
    const onChange = vi.fn();
    renderWithProviders(<SideSwitch view="agent" onChange={onChange} />);

    expect(screen.getByRole("group", { name: "Agent or chat" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Agent" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Chat" })).toHaveAttribute("aria-pressed", "false");

    await userEvent.setup().click(screen.getByRole("button", { name: "Chat" }));
    expect(onChange).toHaveBeenCalledWith("chat");
  });
});
