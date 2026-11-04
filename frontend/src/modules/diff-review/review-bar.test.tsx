import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe, toHaveNoViolations } from "jest-axe";
import { describe, expect, it, vi } from "vitest";

import { ReviewBar, type ReviewBarProps } from "./review-bar";

expect.extend(toHaveNoViolations);

function handlers(): Pick<
  ReviewBarProps,
  "onPrevious" | "onNext" | "onAcceptAll" | "onRejectAll" | "onClose"
> {
  return {
    onPrevious: vi.fn(),
    onNext: vi.fn(),
    onAcceptAll: vi.fn(),
    onRejectAll: vi.fn(),
    onClose: vi.fn(),
  };
}

describe("ReviewBar", () => {
  it("counts the change the keyboard is on, out of all of them", () => {
    render(<ReviewBar index={2} total={5} pending={4} readOnly={false} {...handlers()} />);
    expect(screen.getByText("Change 2 of 5")).toBeInTheDocument();
  });

  it("moves between changes and closes the review through its buttons", async () => {
    const props = handlers();
    render(<ReviewBar index={1} total={3} pending={3} readOnly={false} {...props} />);
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await userEvent.click(screen.getByRole("button", { name: "Previous" }));
    await userEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(props.onNext).toHaveBeenCalledTimes(1);
    expect(props.onPrevious).toHaveBeenCalledTimes(1);
    expect(props.onClose).toHaveBeenCalledTimes(1);
  });

  it("decides every change at once through Accept all and Reject all", async () => {
    const props = handlers();
    render(<ReviewBar index={1} total={3} pending={3} readOnly={false} {...props} />);
    await userEvent.click(screen.getByRole("button", { name: "Accept all" }));
    await userEvent.click(screen.getByRole("button", { name: "Reject all" }));
    expect(props.onAcceptAll).toHaveBeenCalledTimes(1);
    expect(props.onRejectAll).toHaveBeenCalledTimes(1);
  });

  it("disables Accept all when nothing is left, and hides the decisions from a viewer", () => {
    const { unmount } = render(
      <ReviewBar index={3} total={3} pending={0} readOnly={false} {...handlers()} />,
    );
    expect(screen.getByRole("button", { name: "Accept all" })).toBeDisabled();
    unmount();
    render(<ReviewBar index={1} total={3} pending={3} readOnly {...handlers()} />);
    expect(screen.queryByRole("button", { name: "Accept all" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reject all" })).not.toBeInTheDocument();
  });

  it("has no accessibility violations", async () => {
    const { container } = render(
      <ReviewBar index={1} total={3} pending={3} readOnly={false} {...handlers()} />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
