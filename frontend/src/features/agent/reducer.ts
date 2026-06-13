/** Pure, idempotent reducer over spec-44 events → AgentRunState (spec 46). */
import i18n from "@/i18n/config";

import type {
  AgentEvent,
  AgentRunState,
  TranscriptItem,
  WireDiffSummary,
  WireMessage,
} from "./types";

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

export function applyEvent(state: AgentRunState, event: AgentEvent): AgentRunState {
  if (typeof event.seq === "number" && state.seenSeqs.includes(event.seq)) {
    return state; // idempotent: a re-delivered event changes nothing
  }
  const seenSeqs = typeof event.seq === "number" ? [...state.seenSeqs, event.seq] : state.seenSeqs;
  const items = state.items.slice();
  const base: AgentRunState = { ...state, items, seenSeqs };

  switch (event.type) {
    case "token": {
      const idx = openAssistant(items);
      if (idx === -1) {
        items.push({
          kind: "message",
          id: `a-${event.seq ?? items.length}`,
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
      return { ...base, phase: "streaming" };
    }
    case "tool_call": {
      items.push({
        kind: "tool",
        id: event.tool_call_id ?? `tc-${event.seq}`,
        name: event.name ?? "tool",
        args: event.arguments,
        status: "running",
      });
      return { ...base, phase: "streaming" };
    }
    case "tool_result": {
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
    case "diff_proposed": {
      items.push({
        kind: "diff-proposal",
        id: event.diff_id ?? `d-${event.seq}`,
        proposalId: event.diff_id ?? "",
        files: [{ path: event.path ?? "", hunkCount: event.stats?.hunk_count ?? 0 }],
      });
      return base;
    }
    case "done": {
      const idx = openAssistant(items);
      if (idx !== -1) {
        const cur = items[idx];
        if (cur.kind === "message") items[idx] = { ...cur, status: "complete" };
      } else if (event.final_text) {
        items.push({
          kind: "message",
          id: `a-${event.seq}`,
          role: "assistant",
          text: event.final_text,
          status: "complete",
        });
      }
      return { ...base, phase: "done", error: undefined };
    }
    case "error": {
      const code = event.code ?? "internal";
      if (code === "cancelled") {
        const idx = openAssistant(items);
        if (idx !== -1) {
          const cur = items[idx];
          if (cur.kind === "message") items[idx] = { ...cur, status: "cancelled" };
        }
        return { ...base, phase: "cancelled", error: undefined };
      }
      const message = friendlyError(code, event.message ?? "");
      const retryable = RETRYABLE.has(code);
      items.push({ kind: "error", id: `e-${event.seq}`, code, message, retryable });
      return { ...base, phase: "error", error: { code, message, retryable } };
    }
    default:
      return base; // unknown event types are ignored (forward-compatible)
  }
}

/** Convert a loaded transcript (stored messages + open diffs) into render items. */
export function historyToItems(
  messages: WireMessage[],
  diffs: WireDiffSummary[],
): TranscriptItem[] {
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

  const items: TranscriptItem[] = [];
  for (const m of messages) {
    if (m.role === "user") {
      items.push({
        kind: "message",
        id: m.id,
        role: "user",
        text: m.content ?? "",
        status: "complete",
      });
    } else if (m.role === "assistant") {
      for (const tc of m.tool_calls ?? []) {
        const res = toolResults.get(tc.id);
        items.push({
          kind: "tool",
          id: tc.id,
          name: tc.name,
          args: tc.arguments,
          result: res?.summary,
          status: res ? (res.ok ? "ok" : "error") : "running",
        });
      }
      if (m.content) {
        items.push({
          kind: "message",
          id: m.id,
          role: "assistant",
          text: m.content,
          status: "complete",
        });
      }
    }
  }
  for (const d of diffs) {
    items.push({
      kind: "diff-proposal",
      id: d.id,
      proposalId: d.id,
      files: [{ path: d.path, hunkCount: d.stats.hunk_count ?? 0 }],
    });
  }
  return items;
}
