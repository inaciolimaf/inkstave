import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { EditorSettings } from "./types";
import { EditorSettingsPopover } from "./editor-settings-popover";

const SETTINGS: EditorSettings = { fontSize: 14, keymap: "default", lineWrapping: true };

describe("EditorSettingsPopover", () => {
  it("renders a keymap selector and fires onUpdate with the chosen keymap (#62/AC1)", async () => {
    const user = userEvent.setup();
    const onUpdate = vi.fn();
    render(<EditorSettingsPopover settings={SETTINGS} onUpdate={onUpdate} />);

    // Open the popover.
    await user.click(screen.getByLabelText("Editor settings"));

    const keymap = screen.getByLabelText("Keymap");
    expect(keymap).toBeInTheDocument();

    // Open the keymap select and choose "Vim".
    await user.click(keymap);
    await user.click(screen.getByRole("option", { name: "Vim" }));

    expect(onUpdate).toHaveBeenCalledWith({ keymap: "vim" });
  });
});
