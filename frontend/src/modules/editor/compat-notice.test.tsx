import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/utils";

import { CompatNotice, CompatReportDialog } from "./compat-notice";
import type { CompatFinding } from "@/modules/projects";

const findings: CompatFinding[] = [
  {
    ruleId: "eps_figure",
    severity: "info",
    path: "figures/plot.eps",
    line: 4,
    message: "EPS figures need conversion to PDF.",
  },
  {
    ruleId: "latexmkrc",
    severity: "warning",
    path: "latexmkrc",
    line: 1,
    message: "latexmk settings are ignored.",
  },
];

describe("CompatNotice", () => {
  it("counts the things that may not work", () => {
    renderWithProviders(<CompatNotice count={3} onReview={vi.fn()} onDismiss={vi.fn()} />);
    expect(screen.getByText("3 things may not work in Inkstave")).toBeInTheDocument();
  });

  it("uses the singular for one thing", () => {
    renderWithProviders(<CompatNotice count={1} onReview={vi.fn()} onDismiss={vi.fn()} />);
    expect(screen.getByText("1 thing may not work in Inkstave")).toBeInTheDocument();
  });

  it("calls review and dismiss", async () => {
    const onReview = vi.fn();
    const onDismiss = vi.fn();
    renderWithProviders(<CompatNotice count={2} onReview={onReview} onDismiss={onDismiss} />);

    await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(onDismiss).toHaveBeenCalledOnce();
    await userEvent.click(screen.getByRole("button", { name: "Review" }));
    expect(onReview).toHaveBeenCalledOnce();
  });
});

describe("CompatReportDialog", () => {
  it("lists warnings before notes and opens the file at its line", async () => {
    const onOpenLine = vi.fn();
    const onOpenChange = vi.fn();
    renderWithProviders(
      <CompatReportDialog open onOpenChange={onOpenChange} findings={findings} onOpenLine={onOpenLine} />,
    );

    const headings = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(headings).toEqual(["Warnings", "Notes"]);

    await userEvent.click(screen.getByRole("button", { name: /figures\/plot\.eps:4/ }));
    expect(onOpenLine).toHaveBeenCalledWith("figures/plot.eps", 4);
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
