import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { FileDrawer } from "./file-drawer";

describe("FileDrawer", () => {
  it("keeps its content mounted while closed, so the tree keeps its state", () => {
    render(
      <FileDrawer open={false} onClose={vi.fn()}>
        <p>tree</p>
      </FileDrawer>,
    );
    expect(screen.getByText("tree")).not.toBeVisible();
    expect(screen.queryByRole("button", { name: /go back to the text/ })).toBeNull();
  });

  it("closes from the shade and from Escape", async () => {
    const onClose = vi.fn();
    render(
      <FileDrawer open onClose={onClose}>
        <button>row</button>
      </FileDrawer>,
    );
    await userEvent.click(screen.getByRole("button", { name: /go back to the text/ }));
    screen.getByRole("button", { name: "row" }).focus();
    await userEvent.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("leaves Escape to an inline rename", async () => {
    const onClose = vi.fn();
    render(
      <FileDrawer open onClose={onClose}>
        <input aria-label="name" />
      </FileDrawer>,
    );
    screen.getByLabelText("name").focus();
    await userEvent.keyboard("{Escape}");
    expect(onClose).not.toHaveBeenCalled();
  });

  it("returns focus to what opened it", () => {
    const opener = document.createElement("button");
    document.body.append(opener);
    opener.focus();
    const { rerender } = render(<FileDrawer open onClose={vi.fn()} children={<p>x</p>} />);
    expect(document.activeElement).not.toBe(opener);
    rerender(<FileDrawer open={false} onClose={vi.fn()} children={<p>x</p>} />);
    expect(document.activeElement).toBe(opener);
    opener.remove();
  });

  it("offers the outline as a second tab and remembers the one chosen", async () => {
    window.localStorage.removeItem("inkstave:drawer-tab");
    const { unmount } = render(
      <FileDrawer open onClose={vi.fn()} outline={<p>outline</p>}>
        <p>tree</p>
      </FileDrawer>,
    );
    expect(screen.getByText("tree")).toBeVisible();
    await userEvent.click(screen.getByRole("tab", { name: "Outline" }));
    expect(screen.getByText("outline")).toBeVisible();
    expect(screen.getByText("tree")).not.toBeVisible();
    unmount();

    render(
      <FileDrawer open onClose={vi.fn()} outline={<p>outline</p>}>
        <p>tree</p>
      </FileDrawer>,
    );
    expect(screen.getByRole("tab", { name: "Outline" })).toHaveAttribute("aria-selected", "true");
    window.localStorage.removeItem("inkstave:drawer-tab");
  });
});
