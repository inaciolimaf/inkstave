import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { CompileButton } from "./CompileButton";

describe("CompileButton", () => {
  it("renders a Compile action when idle and triggers a compile", async () => {
    const onCompile = vi.fn();
    render(
      <CompileButton state="idle" progressLabel={null} onCompile={onCompile} onCancel={vi.fn()} />,
    );
    const btn = screen.getByRole("button", { name: "Compile project" });
    await userEvent.click(btn);
    expect(onCompile).toHaveBeenCalledTimes(1);
  });

  it("shows a disabled compiling button plus a Cancel button while active", async () => {
    const onCompile = vi.fn();
    const onCancel = vi.fn();
    render(
      <CompileButton
        state="running"
        progressLabel="Compiling…"
        onCompile={onCompile}
        onCancel={onCancel}
      />,
    );
    const compiling = screen.getByRole("button", { name: "Compiling" });
    expect(compiling).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Compile project" })).toBeNull();

    await userEvent.click(screen.getByRole("button", { name: "Cancel compilation" }));
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onCompile).not.toHaveBeenCalled();
  });

  it("returns to a Compile action after a terminal status", () => {
    render(
      <CompileButton state="success" progressLabel={null} onCompile={vi.fn()} onCancel={vi.fn()} />,
    );
    expect(screen.getByRole("button", { name: "Compile project" })).toBeEnabled();
  });
});
