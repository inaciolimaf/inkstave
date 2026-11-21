import { act, renderHook, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/utils";

import { AgentPanel } from "./AgentPanel";
import { DEFAULT_TEXT_SCALE, TEXT_SCALES, readStoredScale, useTextScale } from "./use-text-scale";

vi.mock("./api", () => ({
  listSessions: vi.fn().mockResolvedValue([]),
  createSession: vi.fn(),
  getSession: vi.fn(),
  startRun: vi.fn(),
  stopRun: vi.fn(),
  runEventsUrl: vi.fn(),
}));

const KEY = "inkstave:agent-text-scale";

beforeEach(() => localStorage.clear());

describe("useTextScale", () => {
  it("starts a step above the app's own size", () => {
    const { result } = renderHook(() => useTextScale());
    expect(result.current.scale).toBe(DEFAULT_TEXT_SCALE);
    expect(DEFAULT_TEXT_SCALE).toBeGreaterThan(1);
  });

  it("steps up and down, and remembers the choice", () => {
    const { result } = renderHook(() => useTextScale());
    act(() => result.current.grow());
    expect(result.current.scale).toBe(1.3);
    expect(readStoredScale()).toBe(1.3);
    act(() => result.current.shrink());
    act(() => result.current.shrink());
    expect(result.current.scale).toBe(1);
  });

  it("stops at both ends of the scale", () => {
    const { result } = renderHook(() => useTextScale());
    for (let i = 0; i < TEXT_SCALES.length; i++) act(() => result.current.grow());
    expect(result.current.scale).toBe(TEXT_SCALES.at(-1));
    expect(result.current.canGrow).toBe(false);
    for (let i = 0; i < TEXT_SCALES.length; i++) act(() => result.current.shrink());
    expect(result.current.scale).toBe(TEXT_SCALES[0]);
    expect(result.current.canShrink).toBe(false);
  });

  it("ignores a stored value that is not on the scale", () => {
    localStorage.setItem(KEY, "7");
    expect(readStoredScale()).toBe(DEFAULT_TEXT_SCALE);
  });
});

it("the header buttons resize the conversation's text", async () => {
  renderWithProviders(<AgentPanel projectId="p1" open onOpenChange={vi.fn()} onReviewProposal={vi.fn()} />);
  const scaled = () => document.querySelector<HTMLElement>(".agent-text-scale")!;
  expect(scaled().style.getPropertyValue("--agent-text-scale")).toBe(String(DEFAULT_TEXT_SCALE));
  await userEvent.click(screen.getByRole("button", { name: "Larger text" }));
  await waitFor(() => expect(scaled().style.getPropertyValue("--agent-text-scale")).toBe("1.3"));
  await userEvent.click(screen.getByRole("button", { name: "Smaller text" }));
  await userEvent.click(screen.getByRole("button", { name: "Smaller text" }));
  expect(scaled().style.getPropertyValue("--agent-text-scale")).toBe("1");
});
