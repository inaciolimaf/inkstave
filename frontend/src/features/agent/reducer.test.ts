import { describe, expect, it } from "vitest";

import { applyEvent, historyToItems, initialRunState } from "./reducer";
import type { AgentEvent, AgentRunState } from "./types";

function feed(events: AgentEvent[], start?: AgentRunState): AgentRunState {
  return events.reduce((s, e) => applyEvent(s, e), start ?? initialRunState("s1"));
}

describe("agent reducer", () => {
  it("appends token deltas into one streaming assistant message (AC4)", () => {
    const state = feed([
      { type: "token", seq: 0, text: "Hello " },
      { type: "token", seq: 1, text: "world" },
    ]);
    const msgs = state.items.filter((i) => i.kind === "message");
    expect(msgs).toHaveLength(1);
    expect(msgs[0]).toMatchObject({ role: "assistant", text: "Hello world", status: "streaming" });
    expect(state.phase).toBe("streaming");
  });

  it("correlates tool_call and tool_result (AC5)", () => {
    const state = feed([
      { type: "tool_call", seq: 0, tool_call_id: "c1", name: "read_file", arguments: { x: 1 } },
      {
        type: "tool_result",
        seq: 1,
        tool_call_id: "c1",
        name: "read_file",
        ok: true,
        summary: "ok",
      },
    ]);
    const tool = state.items.find((i) => i.kind === "tool");
    expect(tool).toMatchObject({ id: "c1", name: "read_file", status: "ok" });
  });

  it("pushes a diff-proposal item (AC6)", () => {
    const state = feed([
      { type: "diff_proposed", seq: 0, diff_id: "d1", path: "main.tex", stats: { hunk_count: 3 } },
    ]);
    expect(state.items[0]).toMatchObject({
      kind: "diff-proposal",
      proposalId: "d1",
      files: [{ path: "main.tex", hunkCount: 3 }],
    });
  });

  it("marks the open message complete on done", () => {
    const state = feed([
      { type: "token", seq: 0, text: "Hi" },
      { type: "done", seq: 1, final_text: "Hi" },
    ]);
    expect(state.phase).toBe("done");
    expect(state.items[0]).toMatchObject({ status: "complete" });
  });

  it("marks the open message cancelled on a cancelled error", () => {
    const state = feed([
      { type: "token", seq: 0, text: "Partial" },
      { type: "error", seq: 1, code: "cancelled", message: "Run cancelled." },
    ]);
    expect(state.phase).toBe("cancelled");
    expect(state.items[0]).toMatchObject({ status: "cancelled" });
    expect(state.error).toBeUndefined();
  });

  it("surfaces a non-cancel error with retryable flag (AC8)", () => {
    const state = feed([{ type: "error", seq: 0, code: "internal", message: "boom" }]);
    expect(state.phase).toBe("error");
    expect(state.error).toMatchObject({ code: "internal", retryable: true });
    const limited = feed([{ type: "error", seq: 0, code: "rate_limited", message: "" }]);
    expect(limited.error?.retryable).toBe(true);
    const budget = feed([{ type: "error", seq: 0, code: "budget_exceeded", message: "" }]);
    expect(budget.error?.retryable).toBe(false);
  });

  it("clears a stale error when a terminal done/cancelled lands (spec 50)", () => {
    const afterDone = feed([
      { type: "error", seq: 0, code: "internal", message: "boom" },
      { type: "done", seq: 1, final_text: "ok" },
    ]);
    expect(afterDone.phase).toBe("done");
    expect(afterDone.error).toBeUndefined();

    const afterCancel = feed([
      { type: "error", seq: 0, code: "internal", message: "boom" },
      { type: "error", seq: 1, code: "cancelled", message: "" },
    ]);
    expect(afterCancel.phase).toBe("cancelled");
    expect(afterCancel.error).toBeUndefined();
  });

  it("ignores duplicate seqs and unknown event types (AC11)", () => {
    const state = feed([
      { type: "token", seq: 0, text: "Hi" },
      { type: "token", seq: 0, text: "Hi" }, // duplicate seq → ignored
      { type: "mystery", seq: 1 }, // unknown type → ignored
    ]);
    const msg = state.items.find((i) => i.kind === "message");
    expect(msg).toMatchObject({ text: "Hi" });
    expect(state.items).toHaveLength(1);
  });
});

describe("historyToItems", () => {
  it("renders stored messages, tool calls, and open diffs", () => {
    const items = historyToItems(
      [
        { id: "m0", seq: 0, role: "user", content: "hi", tool_calls: null, tool_call_id: null },
        {
          id: "m1",
          seq: 1,
          role: "assistant",
          content: null,
          tool_calls: [{ id: "c1", name: "read_file", arguments: {} }],
          tool_call_id: null,
        },
        {
          id: "m2",
          seq: 2,
          role: "tool",
          content: '{"ok":true}',
          tool_calls: null,
          tool_call_id: "c1",
        },
        {
          id: "m3",
          seq: 3,
          role: "assistant",
          content: "done",
          tool_calls: null,
          tool_call_id: null,
        },
      ],
      [{ id: "d1", doc_id: "x", path: "main.tex", stats: { hunk_count: 2 }, status: "proposed" }],
    );
    expect(items.map((i) => i.kind)).toEqual(["message", "tool", "message", "diff-proposal"]);
    expect(items[1]).toMatchObject({ kind: "tool", status: "ok" });
  });
});
