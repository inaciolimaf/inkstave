/** Pure, idempotent reducer over spec-44 events → AgentRunState (spec 46). */
import i18n from "@/i18n/config";

import { toFileOp, type WireFileOp } from "./api";
import type { AgentEvent, AgentRunState, TranscriptItem, WireDiffSummary, WireMessage } from "./types";

export function initialRunState(sessionId: string | null = null): AgentRunState {
  return { sessionId, runId: null, phase: "idle", items: [], seenSeqs: [] };
}

const FRIENDLY_ERROR_CODES = new Set([
  "cancelled",
  "agent_rate_limited",
  "rate_limited",
  "agent_budget_exceeded",
  "budget_exceeded",
  "llm_error",
  "internal",
  "timeout",
]);

function friendlyError(code: string, message: string): string {
  if (FRIENDLY_ERROR_CODES.has(code)) return i18n.t(`agent:error.messages.${code}`);
  return message || i18n.t("agent:error.messages.generic");
}

// Rate-limit/transport/internal errors are retryable; a hit budget is not.
const RETRYABLE = new Set([
  "internal",
  "llm_error",
  "rate_limited",
  "agent_rate_limited",
  "transport",
  "timeout",
]);

function openAssistant(items: TranscriptItem[]): number {
  for (let i = items.length - 1; i >= 0; i--) {
    const item = items[i];
    if (item.kind === "message" && item.role === "assistant" && item.status === "streaming") {
      return i;
    }
  }
  return -1;
}

function applyToken(base: AgentRunState, event: AgentEvent): AgentRunState {
  const { items } = base;
  const idx = openAssistant(items);
  if (idx === -1) {
    items.push({
      kind: "message",
      id: `a-${items.length}`,
      role: "assistant",
      text: event.text ?? "",
      status: "streaming",
    });
  } else {
    const cur = items[idx];
    if (cur.kind === "message") {
      items[idx] = { ...cur, text: cur.text + (event.text ?? "") };
    }
  }
  return { ...base, phase: "streaming", activity: { stage: "writing" } };
}

/** Text after a tool call is a new thought, so it must not join the bubble above the call. */
function closeAssistant(items: TranscriptItem[]) {
  const idx = openAssistant(items);
  const cur = items[idx];
  if (cur?.kind === "message") items[idx] = { ...cur, status: "complete" };
}

function applyToolCall(base: AgentRunState, event: AgentEvent): AgentRunState {
  closeAssistant(base.items);
  base.items.push({
    kind: "tool",
    id: event.tool_call_id ?? `tc-${event.seq}`,
    name: event.name ?? "tool",
    args: event.arguments,
    status: "running",
  });
  return { ...base, phase: "streaming", activity: { stage: "tool", tool: event.name } };
}

function applyToolResult(base: AgentRunState, event: AgentEvent): AgentRunState {
  const { items } = base;
  const idx = items.findIndex((it) => it.kind === "tool" && it.id === event.tool_call_id);
  if (idx !== -1) {
    const cur = items[idx];
    if (cur.kind === "tool") {
      items[idx] = {
        ...cur,
        result: event.summary,
        status: event.ok ? "ok" : "error",
        errorText: event.ok ? undefined : event.summary,
      };
    }
  }
  return base;
}

function applyDiffProposed(base: AgentRunState, event: AgentEvent): AgentRunState {
  base.items.push({
    kind: "diff-proposal",
    id: event.diff_id ?? `d-${event.seq}`,
    proposalId: event.diff_id ?? "",
    status: "proposed",
    files: [{ path: event.path ?? "", hunkCount: event.stats?.hunk_count ?? 0 }],
  });
  return base;
}

function applyFileOpProposed(base: AgentRunState, event: AgentEvent): AgentRunState {
  const opId = event.file_op_id ?? "";
  base.items.push({
    kind: "file-op",
    id: opId || `op-${event.seq}`,
    opId,
    opKind: event.kind ?? "create",
    entityType: event.entity_type ?? "doc",
    path: event.path ?? "",
    newPath: event.new_path ?? null,
    affectedPaths: event.affected_paths ?? [],
    status: "proposed",
    rationale: event.rationale ?? null,
  });
  return base;
}

function applyDone(base: AgentRunState, event: AgentEvent): AgentRunState {
  const { items } = base;
  const idx = openAssistant(items);
  if (idx !== -1) {
    const cur = items[idx];
    if (cur.kind === "message") items[idx] = { ...cur, status: "complete" };
  } else if (event.final_text) {
    items.push({
      kind: "message",
      id: `a-${items.length}`,
      role: "assistant",
      text: event.final_text,
      status: "complete",
    });
  }
  return { ...base, phase: "done", error: undefined };
}

function applyCancelled(base: AgentRunState): AgentRunState {
  const { items } = base;
  const idx = openAssistant(items);
  if (idx !== -1) {
    const cur = items[idx];
    if (cur.kind === "message") items[idx] = { ...cur, status: "cancelled" };
  } else {
    // Cancelled before any assistant message opened (e.g. during the tool
    // phase): still surface a cancelled marker so the user sees the run
    // stopped, not a silent transcript (spec 46 §8c).
    items.push({
      kind: "message",
      id: `a-${items.length}`,
      role: "assistant",
      text: "",
      status: "cancelled",
    });
  }
  return { ...base, phase: "cancelled", error: undefined };
}

function applyError(base: AgentRunState, event: AgentEvent): AgentRunState {
  const code = event.code ?? "internal";
  if (code === "cancelled") return applyCancelled(base);
  const message = friendlyError(code, event.message ?? "");
  const retryable = RETRYABLE.has(code);
  closeAssistant(base.items); // the partial reply stops streaming; the next run opens a new bubble
  base.items.push({ kind: "error", id: `e-${base.items.length}`, code, message, retryable });
  return { ...base, phase: "error", error: { code, message, retryable } };
}

export function applyEvent(state: AgentRunState, event: AgentEvent): AgentRunState {
  if (typeof event.seq === "number" && state.seenSeqs.includes(event.seq)) {
    return state; // idempotent: a re-delivered event changes nothing
  }
  const seenSeqs = typeof event.seq === "number" ? [...state.seenSeqs, event.seq] : state.seenSeqs;
  const base: AgentRunState = { ...state, items: state.items.slice(), seenSeqs };

  switch (event.type) {
    case "token":
      return applyToken(base, event);
    case "status":
      if (event.stage === "tool_input") closeAssistant(base.items);
      return { ...base, activity: { stage: event.stage ?? "thinking", tool: event.tool } };
    case "tool_call":
      return applyToolCall(base, event);
    case "tool_result":
      return applyToolResult(base, event);
    case "diff_proposed":
      return applyDiffProposed(base, event);
    case "file_op_proposed":
      return applyFileOpProposed(base, event);
    case "done":
      return applyDone(base, event);
    case "error":
      return applyError(base, event);
    default:
      return base; // unknown event types are ignored (forward-compatible)
  }
}

type HistoryProposal = Extract<TranscriptItem, { kind: "diff-proposal" | "file-op" }>;

function toolResultsOf(messages: WireMessage[]): Map<string, { ok: boolean; summary: unknown }> {
  const toolResults = new Map<string, { ok: boolean; summary: unknown }>();
  for (const m of messages) {
    if (m.role === "tool" && m.tool_call_id) {
      try {
        const parsed = JSON.parse(m.content ?? "{}");
        toolResults.set(m.tool_call_id, {
          ok: !!parsed.ok,
          summary: parsed.error?.message ?? "ok",
        });
      } catch {
        toolResults.set(m.tool_call_id, { ok: false, summary: "unparseable result" });
      }
    }
  }
  return toolResults;
}

function messageItems(
  m: WireMessage,
  toolResults: Map<string, { ok: boolean; summary: unknown }>,
): TranscriptItem[] {
  if (m.role === "user") {
    return [{ kind: "message", id: m.id, role: "user", text: m.content ?? "", status: "complete" }];
  }
  if (m.role !== "assistant") return [];
  const items: TranscriptItem[] = (m.tool_calls ?? []).map((tc) => {
    const res = toolResults.get(tc.id);
    return {
      kind: "tool",
      id: tc.id,
      name: tc.name,
      args: tc.arguments,
      result: res?.summary,
      status: res ? (res.ok ? "ok" : "error") : "running",
    };
  });
  if (m.content) {
    items.push({ kind: "message", id: m.id, role: "assistant", text: m.content, status: "complete" });
  }
  return items;
}

/** A turn's proposals, keyed by the turn's last message (the one they are stored against). */
function proposalsByMessage(
  diffs: WireDiffSummary[],
  fileOps: WireFileOp[],
): Map<string | null, HistoryProposal[]> {
  const byMessage = new Map<string | null, HistoryProposal[]>();
  const add = (messageId: string | null | undefined, item: HistoryProposal) => {
    const key = messageId ?? null;
    byMessage.set(key, [...(byMessage.get(key) ?? []), item]);
  };
  for (const d of diffs) {
    add(d.message_id, {
      kind: "diff-proposal",
      id: d.id,
      proposalId: d.id,
      status: d.status,
      files: [{ path: d.path, hunkCount: d.stats.hunk_count ?? 0 }],
    });
  }
  for (const op of fileOps) add(op.message_id, { kind: "file-op", id: op.id, ...toFileOp(op) });
  return byMessage;
}

/**
 * Convert a loaded transcript (stored messages + proposals) into render items. Each proposal
 * follows the turn that made it, as it did live; one with no known message goes last.
 */
export function historyToItems(
  messages: WireMessage[],
  diffs: WireDiffSummary[],
  fileOps: WireFileOp[] = [],
): TranscriptItem[] {
  const toolResults = toolResultsOf(messages);
  const proposals = proposalsByMessage(diffs, fileOps);
  const items: TranscriptItem[] = [];
  for (const m of messages) {
    items.push(...messageItems(m, toolResults));
    items.push(...(proposals.get(m.id) ?? []));
    proposals.delete(m.id);
  }
  for (const rest of proposals.values()) items.push(...rest);
  return items;
}
