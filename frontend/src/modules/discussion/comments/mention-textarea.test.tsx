import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/utils";

import { MentionTextarea } from "./mention-textarea";

const MEMBERS = [
  { id: "ana", name: "Ana" },
  { id: "ben", name: "Ben Lee" },
];

function Harness({ onPick }: { onPick: (id: string) => void }) {
  const [value, setValue] = useState("");
  return (
    <MentionTextarea
      id="t"
      label="Reply"
      value={value}
      onChange={setValue}
      onPick={(m) => onPick(m.id)}
      members={MEMBERS}
    />
  );
}

describe("MentionTextarea", () => {
  it("offers the members that match the @ word being typed", async () => {
    const user = userEvent.setup();
    renderWithProviders(<Harness onPick={vi.fn()} />);

    await user.type(screen.getByRole("combobox", { name: "Reply" }), "hi @b");

    expect(screen.getByRole("option", { name: "Ben Lee" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Ana" })).not.toBeInTheDocument();
  });

  it("picks with Enter and puts the full name in the text", async () => {
    const user = userEvent.setup();
    const onPick = vi.fn();
    renderWithProviders(<Harness onPick={onPick} />);
    const box = screen.getByRole("combobox", { name: "Reply" });

    await user.type(box, "@a");
    await user.keyboard("{Enter}");

    expect(box).toHaveValue("@Ana ");
    expect(onPick).toHaveBeenCalledWith("ana");
  });

  it("closes the menu with Escape without changing the text", async () => {
    const user = userEvent.setup();
    renderWithProviders(<Harness onPick={vi.fn()} />);
    const box = screen.getByRole("combobox", { name: "Reply" });

    await user.type(box, "@a");
    await user.keyboard("{Escape}");

    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(box).toHaveValue("@a");
  });
});
