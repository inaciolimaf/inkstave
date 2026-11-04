import { render, screen, waitFor } from "@testing-library/react";
import { axe, toHaveNoViolations } from "jest-axe";
import { describe, expect, it, vi } from "vitest";

import { EquationDialog } from "./equation/equation-dialog";
import { SymbolPalette } from "./symbols/symbol-palette";
import { TableBuilder } from "./table/table-builder";
import { makeView } from "./test-view";

expect.extend(toHaveNoViolations);
vi.mock("./equation/mathlive-loader", () => ({ loadMathLive: vi.fn(() => Promise.resolve()) }));

const PLAIN = "\\documentclass{article}\n\\begin{document}\n\n\\end{document}\n";

describe("insert tools accessibility", () => {
  it("the symbol palette has no axe violations", async () => {
    render(<SymbolPalette view={makeView(PLAIN)} mainText={PLAIN} onClose={vi.fn()} />);
    expect(await axe(document.body)).toHaveNoViolations();
  });

  it("the table builder has no axe violations", async () => {
    render(<TableBuilder view={makeView(PLAIN)} mainText={PLAIN} onClose={vi.fn()} />);
    expect(await axe(document.body)).toHaveNoViolations();
  });

  it("the equation editor has no axe violations, with the formula field loaded", async () => {
    render(<EquationDialog view={makeView("$x$", 1)} onClose={vi.fn()} />);
    await waitFor(() => expect(document.querySelector("math-field")).not.toBeNull());
    expect(screen.getByRole("dialog", { name: "Equation" })).toBeInTheDocument();
    expect(await axe(document.body)).toHaveNoViolations();
  });
});
