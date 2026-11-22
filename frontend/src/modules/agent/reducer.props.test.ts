/** Property tests for the agent run reducer (spec 46): many runs, repeated events, any terminal. */
import fc from "fast-check";
import { describe, expect, it } from "vitest";

import { applyEvent, initialRunState } from "./reducer";
import type { AgentEvent, AgentRunState } from "./types";

const OPTIONS = { numRuns: 50 };

type Ending = "done" | "error" | "cancelled";

interface RunPlan {
  runId: string;
  /** Token texts per segment; a tool call separates two segments, and each closes the bubble above it. */
  segments: string[][];
  ending: Ending;
}

const token = fc.stringMatching(/^[a-zA-Z é]{1,5}$/);
const runPlan = (index: number): fc.Arbitrary<RunPlan> =>
  fc.record({
    runId: fc.constant(`run-${index}`),
    segments: fc.array(fc.array(token, { minLength: 1, maxLength: 4 }), { minLength: 1, maxLength: 3 }),
    ending: fc.constantFrom<Ending>("done", "error", "cancelled"),
  });

/** The events of one run, numbered from 0 in delivery order, as the server emits them. */
function eventsOf(plan: RunPlan): AgentEvent[] {
  const events: AgentEvent[] = [];
  const push = (event: Omit<AgentEvent, "seq" | "run_id">) =>
    events.push({ ...event, run_id: plan.runId, seq: events.length });
  plan.segments.forEach((segment, index) => {
    if (index > 0) {
      const toolCallId = `${plan.runId}-tool-${index}`;
      push({ type: "tool_call", tool_call_id: toolCallId, name: "read_file", arguments: {} });
      push({ type: "tool_result", tool_call_id: toolCallId, ok: true, summary: "ok" });
    }
    for (const text of segment) push({ type: "token", text });
  });
  if (plan.ending === "done") push({ type: "done", final_text: null });
  if (plan.ending === "error") push({ type: "error", code: "llm_error", message: "boom" });
  if (plan.ending === "cancelled") push({ type: "error", code: "cancelled", message: "stopped" });
  return events;
}

/** Re-deliveries: after event i, re-send any earlier event picked by `picks[i]` (never a later one). */
function withDuplicates(events: AgentEvent[], picks: number[][]): AgentEvent[] {
  const stream: AgentEvent[] = [];
  events.forEach((event, index) => {
    stream.push(event);
    for (const pick of picks[index] ?? []) stream.push(events[pick % (index + 1)]);
  });
  return stream;
}

function feed(state: AgentRunState, events: AgentEvent[]): AgentRunState {
  return events.reduce(applyEvent, state);
}

/** The assistant text the transcript shows, bubble by bubble, skipping empty markers. */
function assistantTexts(state: AgentRunState): string[] {
  return state.items.flatMap((item) =>
    item.kind === "message" && item.role === "assistant" && item.text !== "" ? [item.text] : [],
  );
}

const expectedTexts = (plan: RunPlan) => plan.segments.map((segment) => segment.join(""));
function streamOf(plan: RunPlan, picks: number[][]): AgentEvent[] {
  return withDuplicates(eventsOf(plan), picks);
}

const picksFor = (length: number) => fc.array(fc.array(fc.nat(), { maxLength: 2 }), { maxLength: length });

describe("agent reducer properties", () => {
  it("a run with repeated events ends with its text once, not running, and as if delivered once", () => {
    fc.assert(
      fc.property(runPlan(0), picksFor(64), (plan, picks) => {
        const stream = streamOf(plan, picks);
        const once = eventsOf(plan);
        const state = feed(initialRunState("s"), stream);
        expect(state.phase).toBe(plan.ending);
        expect(state.items.some((i) => i.kind === "message" && i.status === "streaming")).toBe(false);
        expect(assistantTexts(state)).toEqual(expectedTexts(plan));
        expect(feed(initialRunState("s"), once)).toEqual(state);
      }),
      OPTIONS,
    );
  });

  it("a sequence of runs shows every run's text exactly once and none stays running", () => {
    fc.assert(
      fc.property(
        fc
          .integer({ min: 1, max: 4 })
          .chain((count) => fc.tuple(...Array.from({ length: count }, (_, i) => runPlan(i)))),
        fc.array(picksFor(64), { minLength: 4, maxLength: 4 }),
        (plans, picksPerRun) => {
          let state = initialRunState("s");
          plans.forEach((plan, index) => {
            // seq restarts at 0 for each run, so the chat clears seenSeqs when a run starts
            state = feed({ ...state, seenSeqs: [] }, streamOf(plan, picksPerRun[index] ?? []));
          });
          const expected = plans.flatMap(expectedTexts);
          expect(assistantTexts(state)).toEqual(expected);
          expect(state.items.some((i) => i.kind === "message" && i.status === "streaming")).toBe(false);
        },
      ),
      OPTIONS,
    );
  });
});
