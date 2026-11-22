import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Button } from "./button";

describe("Button", () => {
  it("renders type=button by default, so it does not submit a surrounding form", () => {
    render(<Button>Save</Button>);
    expect(screen.getByRole("button", { name: "Save" })).toHaveAttribute("type", "button");
  });

  it("keeps an explicit type=submit", () => {
    render(<Button type="submit">Send</Button>);
    expect(screen.getByRole("button", { name: "Send" })).toHaveAttribute("type", "submit");
  });

  it("adds no type when it renders the caller's element through asChild", () => {
    render(
      <Button asChild>
        <a href="/help">Help</a>
      </Button>,
    );
    expect(screen.getByRole("link", { name: "Help" })).not.toHaveAttribute("type");
  });
});
