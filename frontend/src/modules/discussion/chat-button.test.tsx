import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/utils";

import { ChatButton } from "./chat-button";

describe("ChatButton", () => {
  it("names the unread count in its accessible name and shows it", async () => {
    const onOpen = vi.fn();
    renderWithProviders(<ChatButton unread={3} onOpen={onOpen} />);
    const button = screen.getByRole("button", { name: "Chat, 3 unread" });
    expect(button).toHaveTextContent("3");
    await userEvent.setup().click(button);
    expect(onOpen).toHaveBeenCalledTimes(1);
  });

  it("shows no badge when nothing is unread", () => {
    renderWithProviders(<ChatButton unread={0} onOpen={() => undefined} />);
    const button = screen.getByRole("button", { name: "Chat" });
    expect(button).not.toHaveTextContent(/\d/);
  });

  it("caps the badge at 99+", () => {
    renderWithProviders(<ChatButton unread={120} onOpen={() => undefined} />);
    expect(screen.getByRole("button", { name: "Chat, 120 unread" })).toHaveTextContent("99+");
  });
});
