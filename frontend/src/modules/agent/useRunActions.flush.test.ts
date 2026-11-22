/** A send waits for the editor's flush before the run starts, so the agent reads the text the user just typed. */
import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { startRun } from "./api";
import { initialRunState } from "./reducer";
import type { AgentRunState } from "./types";
import { useRunActions } from "./useRunActions";

vi.mock("./api", () => ({
  startRun: vi.fn(),
  stopRun: vi.fn(),
}));

function setup(onBeforeSend: () => Promise<void>) {
  const run: AgentRunState = initialRunState("s1");
  const { result } = renderHook(() =>
    useRunActions({
      projectId: "p1",
      run,
      setRun: vi.fn(),
      activeSessionId: "s1",
      createActiveSession: () => Promise.resolve("s1"),
      openStream: vi.fn(),
      onBeforeSend,
    }),
  );
  return result;
}

beforeEach(() => {
  vi.mocked(startRun).mockReset();
  vi.mocked(startRun).mockResolvedValue({ runId: "r1" } as unknown as Awaited<ReturnType<typeof startRun>>);
});

describe("send and the pending editor flush", () => {
  it("starts the run only after the flush has resolved", async () => {
    let finishFlush: () => void = () => undefined;
    const flush = new Promise<void>((resolve) => {
      finishFlush = resolve;
    });
    const result = setup(() => flush);

    let sent: Promise<boolean> = Promise.resolve(false);
    act(() => {
      sent = result.current.send("rewrite the intro");
    });
    await act(() => Promise.resolve());
    expect(startRun).not.toHaveBeenCalled();

    await act(async () => {
      finishFlush();
      await sent;
    });
    expect(startRun).toHaveBeenCalledWith("p1", "s1", "rewrite the intro");
  });

  it("still starts the run when the flush rejects", async () => {
    const result = setup(() => Promise.reject(new Error("socket gone")));
    await act(async () => {
      await result.current.send("hello");
    });
    expect(startRun).toHaveBeenCalledWith("p1", "s1", "hello");
  });
});
