import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { initialRunState } from "./reducer";
import { RunStatus, formatElapsed, runStatusKey } from "./run-status";
import type { AgentRunState } from "./types";

const run = (over: Partial<AgentRunState>): AgentRunState => ({ ...initialRunState("s1"), ...over });

describe("runStatusKey", () => {
  it("follows the run from sending to stopping", () => {
    expect(runStatusKey(run({ phase: "starting" }))).toBe("run.stages.sending");
    expect(runStatusKey(run({ phase: "streaming" }))).toBe("run.stages.queued");
    expect(runStatusKey(run({ phase: "streaming", activity: { stage: "thinking" } }))).toBe(
      "run.stages.thinking",
    );
    expect(runStatusKey(run({ phase: "streaming", activity: { stage: "tool", tool: "read_file" } }))).toBe(
      "run.tools.read_file",
    );
    expect(runStatusKey(run({ phase: "stopping", activity: { stage: "writing" } }))).toBe(
      "run.stages.stopping",
    );
  });
});

describe("formatElapsed", () => {
  it("reads as seconds, then minutes", () => {
    expect(formatElapsed(12_400)).toBe("12 s");
    expect(formatElapsed(65_000)).toBe("1 min 5 s");
  });
});

describe("RunStatus", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(100_000);
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("counts the time and says so when nothing has happened for a minute", () => {
    render(
      <RunStatus run={run({ phase: "streaming", startedAt: 100_000, activity: { stage: "thinking" } })} />,
    );
    expect(screen.getByRole("status")).toHaveTextContent("Thinking…");
    act(() => {
      vi.advanceTimersByTime(61_000);
    });
    expect(screen.getByText("1 min 1 s")).toBeInTheDocument();
    expect(screen.getByText(/No news for a while/)).toBeInTheDocument();
  });

  it("stays calm while events keep coming", () => {
    const state = run({ phase: "streaming", startedAt: 0, lastEventAt: 99_000 });
    render(<RunStatus run={state} />);
    expect(screen.queryByText(/No news/)).not.toBeInTheDocument();
  });

  it("names a tool it has no sentence for in general words", () => {
    const state = run({
      phase: "streaming",
      startedAt: 100_000,
      activity: { stage: "tool", tool: "new_tool" },
    });
    render(<RunStatus run={state} />);
    expect(screen.getByRole("status")).toHaveTextContent("Using a tool…");
  });
});
