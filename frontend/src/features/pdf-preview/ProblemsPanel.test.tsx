import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ProblemsPanel } from "./ProblemsPanel";
import type { CompileProblems, Problem } from "./problems";

function problem(over: Partial<Problem>): Problem {
  return {
    severity: "error",
    message: "msg",
    file: "main.tex",
    line: 1,
    end_line: null,
    raw: "",
    rule: "tex-error",
    ...over,
  };
}

function compileProblems(problems: Problem[]): CompileProblems {
  return {
    compile_id: "c1",
    errors: problems.filter((p) => p.severity === "error").length,
    warnings: problems.filter((p) => p.severity === "warning").length,
    infos: problems.filter((p) => p.severity === "info").length,
    problems,
  };
}

describe("ProblemsPanel", () => {
  it("groups problems by severity with counts", () => {
    render(
      <ProblemsPanel
        problems={compileProblems([
          problem({ message: "Undefined control sequence", line: 42 }),
          problem({ severity: "warning", message: "Reference undefined", line: 10 }),
          problem({ severity: "info", message: "Overfull hbox", line: 5 }),
        ])}
      />,
    );
    expect(screen.getByText("Errors (1)")).toBeInTheDocument();
    expect(screen.getByText("Warnings (1)")).toBeInTheDocument();
    expect(screen.getByText("Typesetting (1)")).toBeInTheDocument();
    expect(screen.getByText("Undefined control sequence")).toBeInTheDocument();
  });

  it("jumps to the source line when a locatable row is clicked", async () => {
    const onJump = vi.fn();
    render(
      <ProblemsPanel
        problems={compileProblems([
          problem({ message: "Boom", file: "sections/intro.tex", line: 7 }),
        ])}
        onJump={onJump}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /error: Boom/i }));
    expect(onJump).toHaveBeenCalledWith("sections/intro.tex", 7);
  });

  it("disables rows without a file/line", () => {
    render(
      <ProblemsPanel
        problems={compileProblems([problem({ message: "Generic", file: null, line: null })])}
        onJump={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: /error: Generic/i })).toBeDisabled();
  });

  it("shows an empty state with no problems", () => {
    render(<ProblemsPanel problems={compileProblems([])} />);
    expect(screen.getByText("No problems.")).toBeInTheDocument();
  });

  it("prompts to compile when no log is available", () => {
    render(<ProblemsPanel problems={null} reason="log_unavailable" />);
    expect(screen.getByText("No log yet — run a compile.")).toBeInTheDocument();
  });
});
