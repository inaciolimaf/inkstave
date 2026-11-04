import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { makeView } from "../test-view";

import { EquationDialog } from "./equation-dialog";
import { loadMathLive } from "./mathlive-loader";

// MathLive is never loaded in the tests: the loader is replaced, and `<math-field>` stays an unknown element.
vi.mock("./mathlive-loader", () => ({ loadMathLive: vi.fn(() => Promise.resolve()) }));

const loader = vi.mocked(loadMathLive);

/** Sets the formula the way an edit in the field does. */
function setLatex(field: HTMLElement & { value: string }, latex: string) {
  act(() => {
    field.value = latex;
    field.dispatchEvent(new Event("input"));
  });
}

/** The formula field the dialog created, after MathLive "loaded". */
async function mathField(): Promise<HTMLElement & { value: string }> {
  await waitFor(() => expect(document.querySelector("math-field")).not.toBeNull());
  return document.querySelector("math-field") as HTMLElement & { value: string };
}

beforeEach(() => {
  loader.mockReset();
  loader.mockImplementation(() => Promise.resolve());
});

describe("EquationDialog", () => {
  it("opens on the math the cursor is in, showing it in the formula editor", async () => {
    const view = makeView("Let $\\frac{a}{b}$ hold.", 9);
    render(<EquationDialog view={view} onClose={vi.fn()} />);
    const field = await mathField();
    expect(field.value).toBe("\\frac{a}{b}");
  });

  it("replaces only the body on Save, so the $ delimiters stay", async () => {
    const user = userEvent.setup();
    const view = makeView("$\\frac{a}{b}$", 4);
    const onClose = vi.fn();
    render(<EquationDialog view={view} onClose={onClose} />);
    const field = await mathField();
    setLatex(field, "\\frac{a}{c}");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(view.state.doc.toString()).toBe("$\\frac{a}{c}$");
    expect(onClose).toHaveBeenCalled();
  });

  it("changes nothing on Cancel", async () => {
    const user = userEvent.setup();
    const view = makeView("$x$", 2);
    const onClose = vi.fn();
    render(<EquationDialog view={view} onClose={onClose} />);
    const field = await mathField();
    setLatex(field, "y");
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(view.state.doc.toString()).toBe("$x$");
    expect(onClose).toHaveBeenCalled();
  });

  it("opens empty outside math, and inserts inline \\( \\) math on Save", async () => {
    const user = userEvent.setup();
    const view = makeView("Text ", 5);
    render(<EquationDialog view={view} onClose={vi.fn()} />);
    const field = await mathField();
    expect(field.value).toBe("");
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    setLatex(field, "\\alpha");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(view.state.doc.toString()).toBe("Text \\(\\alpha\\)");
  });

  it("inserts an equation environment when the display toggle is on", async () => {
    const user = userEvent.setup();
    const view = makeView("", 0);
    render(<EquationDialog view={view} onClose={vi.fn()} />);
    const field = await mathField();
    setLatex(field, "E=mc^2");
    await user.click(screen.getByRole("checkbox", { name: "Display (centred)" }));
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(view.state.doc.toString()).toBe("\\begin{equation}\nE=mc^2\n\\end{equation}");
  });

  it("shows a spinner while MathLive loads, and never blocks the document", () => {
    loader.mockImplementation(() => new Promise<void>(() => {}));
    const view = makeView("$x$", 1);
    render(<EquationDialog view={view} onClose={vi.fn()} />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading the equation editor…");
    expect(view.state.doc.toString()).toBe("$x$");
  });

  it("falls back to a plain textarea with the LaTeX when MathLive fails to load", async () => {
    const user = userEvent.setup();
    loader.mockImplementation(() => Promise.reject(new Error("offline")));
    const view = makeView("$x^2$", 2);
    render(<EquationDialog view={view} onClose={vi.fn()} />);
    const textarea = await screen.findByRole("textbox", { name: "LaTeX of the equation" });
    expect(textarea).toHaveValue("x^2");
    expect(document.querySelector("math-field")).toBeNull();
    await user.clear(textarea);
    await user.type(textarea, "y^2");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(view.state.doc.toString()).toBe("$y^2$");
  });

  it("hides the virtual keyboard toggle until the formula editor is ready", async () => {
    loader.mockImplementation(() => Promise.reject(new Error("offline")));
    render(<EquationDialog view={makeView("")} onClose={vi.fn()} />);
    await screen.findByRole("textbox", { name: "LaTeX of the equation" });
    expect(screen.queryByRole("checkbox", { name: "Virtual keyboard" })).toBeNull();
  });
});
