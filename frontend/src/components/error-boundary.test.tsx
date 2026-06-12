import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ErrorBoundary } from "./error-boundary";

function Thrower({ boom }: { boom: boolean }): React.ReactElement {
  if (boom) throw new Error("kaboom");
  return <div>healthy child</div>;
}

beforeEach(() => {
  // React logs caught render errors to console.error — silence the expected noise.
  vi.spyOn(console, "error").mockImplementation(() => {});
});
afterEach(() => vi.restoreAllMocks());

describe("ErrorBoundary", () => {
  it("renders the fallback when a child throws during render (AC1)", () => {
    render(
      <ErrorBoundary>
        <Thrower boom />
      </ErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("Something went wrong")).toBeInTheDocument();
    expect(screen.queryByText("healthy child")).not.toBeInTheDocument();
  });

  it("exposes a recovery action in the fallback (AC2)", () => {
    render(
      <ErrorBoundary>
        <Thrower boom />
      </ErrorBoundary>,
    );
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reload/i })).toBeInTheDocument();
  });

  it("renders children unchanged when nothing throws (AC3)", () => {
    render(
      <ErrorBoundary>
        <Thrower boom={false} />
      </ErrorBoundary>,
    );
    expect(screen.getByText("healthy child")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("recovers when 'Try again' is clicked after the child stops throwing (AC2)", async () => {
    function Wrapper() {
      return (
        <ErrorBoundary>
          <Thrower boom={shouldThrow} />
        </ErrorBoundary>
      );
    }
    let shouldThrow = true;
    const { rerender } = render(<Wrapper />);
    expect(screen.getByRole("alert")).toBeInTheDocument();

    // Update the tree so the child no longer throws, then reset the boundary.
    shouldThrow = false;
    rerender(<Wrapper />);
    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(screen.getByText("healthy child")).toBeInTheDocument();
  });
});
