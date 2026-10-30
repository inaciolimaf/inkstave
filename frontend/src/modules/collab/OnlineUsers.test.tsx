import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { OnlineUsers } from "./OnlineUsers";
import type { PresenceUser } from "./usePresence";

function user(over: Partial<PresenceUser>): PresenceUser {
  return { id: "u", name: "User", color: "#2563eb", idle: false, isLocal: false, ...over };
}

describe("OnlineUsers", () => {
  it("renders nothing when no one is online (solo/empty, AC9)", () => {
    const { container } = render(<OnlineUsers users={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows one avatar per present user, marking the local user (AC4)", () => {
    render(
      <OnlineUsers
        users={[user({ id: "me", name: "Me", isLocal: true }), user({ id: "a", name: "Alice" })]}
      />,
    );
    expect(screen.getByLabelText("Me (You) — online")).toBeInTheDocument();
    expect(screen.getByLabelText("Alice — online")).toBeInTheDocument();
  });

  it("dims an idle user (AC6)", () => {
    render(<OnlineUsers users={[user({ id: "a", name: "Alice", idle: true })]} />);
    expect(screen.getByLabelText("Alice — idle")).toBeInTheDocument();
  });

  it("collapses overflow into a +N popover (AC5)", async () => {
    const users = Array.from({ length: 8 }, (_, i) => user({ id: `u${i}`, name: `User ${i}` }));
    render(<OnlineUsers users={users} max={5} />);
    const overflow = screen.getByRole("button", { name: "3 more online" });
    expect(overflow).toHaveTextContent("+3");
    await userEvent.click(overflow);
    expect(screen.getByText("User 7 — online")).toBeInTheDocument();
  });
});
