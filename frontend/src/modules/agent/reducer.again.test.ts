/**
 * "Do it again" lifecycle tests for the agent reducer: a second run, a run after a
 * cancel or an error, and a transcript rebuilt from the session detail. Every run
 * numbers its events from 0, so the page clears the seen numbers before each run (as
 * useRunActions does); these tests replay that contract.
 */
import { describe, expect, it } from "vitest";

import { applyEvent, historyToItems, initialRunState } from "./reducer";
import type { AgentEvent, AgentRunState, WireMessage } from "./types";

const ACTIVE = ["starting", "streaming", "stopping"];

/** What useRunActions.send does to the state before a run's first event arrives. */
function startRun(state: AgentRunState, text: string): AgentRunState {
  return {
    ...state,
    phase: "starting",
    error: undefined,
    seenSeqs: [],
    items: [...state.items, { kind: "message", id: `u-${text}`, role: "user", text, status: "complete" }],
  };
}

function feed(state: AgentRunState, events: AgentEvent[]): AgentRunState {
  return events.reduce((s, e) => applyEvent(s, e), state);
}

const assistantTexts = (s: AgentRunState) =>
  s.items.flatMap((i) => (i.kind === "message" && i.role === "assistant" ? [i.text] : []));

describe("agent reducer, do it again", () => {
  it("runs three times in one chat with overlapping seq numbers and ends every run", () => {
    let state = initialRunState("s1");
    for (const word of ["alpha", "beta", "gamma"]) {
      state = feed(startRun(state, `ask ${word}`), [
        { type: "token", seq: 0, text: `${word} ` },
        { type: "token", seq: 1, text: "answer" },
        { type: "done", seq: 2, final_text: `${word} answer`, usage: {}, iterations: 1 },
      ]);
      expect(state.phase).toBe("done");
      expect(ACTIVE).not.toContain(state.phase);
    }
    expect(assistantTexts(state)).toEqual(["alpha answer", "beta answer", "gamma answer"]);
    expect(state.items.filter((i) => i.kind === "message" && i.status === "streaming")).toHaveLength(0);
  });

  it("drops a run's events when the seen numbers are not cleared (the regression of 84dd5cb)", () => {
    // Documents why the reset exists: without it the second run is truncated.
    const first = feed(initialRunState("s1"), [
      { type: "token", seq: 0, text: "One " },
      { type: "token", seq: 1, text: "two" },
    ]);
    const stale = feed(first, [{ type: "token", seq: 0, text: "Alpha " }]);
    expect(assistantTexts(stale)).toEqual(["One two"]);
  });

  it("starts cleanly after a cancel", () => {
    let state = feed(startRun(initialRunState("s1"), "first"), [
      { type: "token", seq: 0, text: "Working" },
      { type: "error", seq: 1, code: "cancelled", message: "Run cancelled." },
    ]);
    expect(state.phase).toBe("cancelled");
    expect(ACTIVE).not.toContain(state.phase);

    state = feed(startRun(state, "second"), [
      { type: "token", seq: 0, text: "Fresh" },
      { type: "done", seq: 1, final_text: "Fresh", usage: {}, iterations: 1 },
    ]);
    expect(state.phase).toBe("done");
    expect(state.items.at(-1)).toMatchObject({ kind: "message", role: "assistant", text: "Fresh" });
    expect(state.items.some((i) => i.kind === "message" && i.status === "cancelled")).toBe(true);
  });

  it("recovers after an error run and ends the spinner on the error", () => {
    let state = feed(startRun(initialRunState("s1"), "first"), [
      { type: "status", seq: 0, stage: "thinking" },
      { type: "error", seq: 1, code: "llm_error", message: "upstream" },
    ]);
    expect(state.phase).toBe("error");
    expect(ACTIVE).not.toContain(state.phase);
    expect(state.error).toMatchObject({ code: "llm_error", retryable: true });

    state = feed(startRun(state, "retry"), [
      { type: "token", seq: 0, text: "Recovered" },
      { type: "done", seq: 1, final_text: "Recovered", usage: {}, iterations: 1 },
    ]);
    expect(state.phase).toBe("done");
    expect(state.error).toBeUndefined();
    expect(assistantTexts(state)).toContain("Recovered");
  });

  it("keeps a proposal next to the turn that made it, live and after a reload", () => {
    // Live: the proposal arrives after the assistant's text of the turn.
    const live = feed(startRun(initialRunState("s1"), "change it"), [
      { type: "token", seq: 0, text: "Here is the edit" },
      { type: "diff_proposed", seq: 1, diff_id: "d1", path: "main.tex", stats: { hunk_count: 1 } },
      { type: "done", seq: 2, final_text: "Here is the edit", usage: {}, iterations: 1 },
    ]);
    expect(live.items.map((i) => i.kind)).toEqual(["message", "message", "diff-proposal"]);

    // After a reload: the same turn, rebuilt from the stored messages and proposals.
    const messages: WireMessage[] = [
      { id: "m1", seq: 0, role: "user", content: "change it", tool_calls: null, tool_call_id: null },
      { id: "m2", seq: 1, role: "assistant", content: "Here is the edit", tool_calls: null, tool_call_id: null },
      { id: "m3", seq: 2, role: "user", content: "and again", tool_calls: null, tool_call_id: null },
      { id: "m4", seq: 3, role: "assistant", content: "Done", tool_calls: null, tool_call_id: null },
    ];
    const diffs = [
      { id: "d1", message_id: "m2", doc_id: "doc", path: "main.tex", status: "proposed", stats: { hunk_count: 1 } },
    ];
    const reloaded = historyToItems(messages, diffs);
    const ids = reloaded.map((i) => (i.kind === "diff-proposal" ? "proposal" : i.id));
    expect(ids).toEqual(["m1", "m2", "proposal", "m3", "m4"]);
  });

  it("puts a proposal whose turn is unknown last, and does not drop it", () => {
    const messages: WireMessage[] = [
      { id: "m1", seq: 0, role: "user", content: "a", tool_calls: null, tool_call_id: null },
      { id: "m2", seq: 1, role: "assistant", content: "b", tool_calls: null, tool_call_id: null },
    ];
    const diffs = [{ id: "orphan", message_id: "gone", doc_id: "doc", path: "x.tex", status: "proposed", stats: {} }];
    const items = historyToItems(messages, diffs);
    expect(items.at(-1)).toMatchObject({ kind: "diff-proposal", proposalId: "orphan" });
  });
});
