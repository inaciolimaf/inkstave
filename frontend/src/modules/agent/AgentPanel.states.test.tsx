import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/utils";

import { AgentPanel } from "./AgentPanel";
import type { AgentRunState } from "./types";

const chat = vi.hoisted(() => ({
  value: {
    sessions: [] as unknown[],
    activeSessionId: null as string | null,
    run: { runId: null, sessionId: null, phase: "idle", items: [], seenSeqs: [] } as AgentRunState,
    transcriptLoading: false,
    send: vi.fn(),
    stop: vi.fn(),
    retry: vi.fn(),
    selectSession: vi.fn(),
    newChat: vi.fn(),
  },
}));
vi.mock("./useAgentChat", () => ({ useAgentChat: () => chat.value }));

afterEach(() => vi.clearAllMocks());

function renderPanel() {
  return renderWithProviders(
    <AgentPanel projectId="p1" open onOpenChange={vi.fn()} onReviewProposal={vi.fn()} />,
  );
}

describe("AgentPanel states (spec 64)", () => {
  it("shows a loading affordance while the transcript loads with no items (AC6)", () => {
    chat.value.transcriptLoading = true;
    chat.value.run = { runId: null, sessionId: null, phase: "idle", items: [], seenSeqs: [] };
    chat.value.run.error = undefined;
    renderPanel();
    expect(screen.getByRole("status", { name: /loading conversation/i })).toBeInTheDocument();
  });

  it("shows AgentErrorState when the run errored (AC7)", () => {
    chat.value.transcriptLoading = false;
    chat.value.run = {
      runId: "r1",
      sessionId: "s1",
      phase: "error",
      items: [],
      seenSeqs: [],
      error: { code: "llm_error", message: "AI hiccup", retryable: true },
    };
    renderPanel();
    expect(screen.getByText("AI hiccup")).toBeInTheDocument();
  });
});
