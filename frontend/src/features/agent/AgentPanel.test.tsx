import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/utils";

import { AgentPanel } from "./AgentPanel";

const api = vi.hoisted(() => ({
  listSessions: vi.fn(),
  createSession: vi.fn(),
  getSession: vi.fn(),
  startRun: vi.fn(),
  stopRun: vi.fn(),
  runEventsUrl: vi.fn(() => "http://x/events"),
}));
vi.mock("./api", () => api);

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  listeners: Record<string, ((e: { data: string }) => void)[]> = {};
  onerror: (() => void) | null = null;
  closed = false;
  constructor(public url: string) {
    FakeEventSource.instances.push(this);
  }
  addEventListener(type: string, fn: (e: { data: string }) => void) {
    (this.listeners[type] ??= []).push(fn);
  }
  close() {
    this.closed = true;
  }
  emit(event: Record<string, unknown>) {
    (this.listeners[event.type as string] ?? []).forEach((fn) =>
      fn({ data: JSON.stringify(event) }),
    );
  }
}

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
  api.listSessions.mockResolvedValue([]);
  api.createSession.mockResolvedValue({ id: "s1", projectId: "p1", title: null, runState: "idle" });
  api.startRun.mockResolvedValue({ runId: "r1", streamUrl: "http://x/events" });
  api.stopRun.mockResolvedValue(undefined);
});
afterEach(() => vi.unstubAllGlobals());

function renderPanel(onReview = vi.fn()) {
  return renderWithProviders(
    <AgentPanel projectId="p1" open onOpenChange={vi.fn()} onReviewProposal={onReview} />,
  );
}

describe("AgentPanel", () => {
  it("prefills the composer from an example chip (AC2)", async () => {
    renderPanel();
    const chip = await screen.findByText("Rewrite the introduction to be more concise.");
    await userEvent.click(chip);
    expect(screen.getByLabelText("Message the agent")).toHaveValue(
      "Rewrite the introduction to be more concise.",
    );
  });

  it("sends a message and streams the response (AC3, AC4, AC6)", async () => {
    const onReview = vi.fn();
    renderPanel(onReview);
    await userEvent.click(
      await screen.findByText("Find where the methodology section is defined."),
    );
    await userEvent.click(screen.getByLabelText("Send message"));

    // The user message appears and a run is started.
    await screen.findByText("Find where the methodology section is defined.");
    await waitFor(() => expect(api.startRun).toHaveBeenCalledWith("p1", "s1", expect.any(String)));
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    const es = FakeEventSource.instances[0];

    es.emit({ type: "token", seq: 0, text: "Found it " });
    es.emit({ type: "token", seq: 1, text: "in main.tex" });
    await screen.findByText(/Found it in main\.tex/);

    es.emit({
      type: "diff_proposed",
      seq: 2,
      diff_id: "d9",
      path: "main.tex",
      stats: { hunk_count: 1 },
    });
    await userEvent.click(await screen.findByRole("button", { name: /Review changes/ }));
    expect(onReview).toHaveBeenCalledWith("d9");

    es.emit({ type: "done", seq: 3, final_text: "Found it in main.tex", usage: {}, iterations: 1 });
    // Composer re-enabled after the run finishes.
    await waitFor(() => expect(screen.getByLabelText("Message the agent")).not.toBeDisabled());
  });

  it("Stop cancels the run and marks the message cancelled (AC7)", async () => {
    renderPanel();
    await userEvent.click(await screen.findByText("Add a conclusion summarising the key results."));
    await userEvent.click(screen.getByLabelText("Send message"));
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    const es = FakeEventSource.instances[0];
    es.emit({ type: "token", seq: 0, text: "Working" });

    await userEvent.click(await screen.findByRole("button", { name: "Stop the run" }));
    expect(api.stopRun).toHaveBeenCalledWith("p1", "s1", "r1");

    es.emit({ type: "error", seq: 1, code: "cancelled", message: "Run cancelled." });
    await screen.findByText("Run cancelled");
    await waitFor(() => expect(screen.getByLabelText("Message the agent")).not.toBeDisabled());
  });

  it("lists sessions and starts a new chat (AC9)", async () => {
    api.listSessions.mockResolvedValue([
      { id: "old", projectId: "p1", title: "Older chat", runState: "idle" },
    ]);
    api.getSession.mockResolvedValue({
      session: { id: "old", projectId: "p1", title: "Older chat", runState: "idle" },
      messages: [
        { id: "m", seq: 0, role: "user", content: "prior", tool_calls: null, tool_call_id: null },
      ],
      diffs: [],
    });
    renderPanel();
    await userEvent.click(await screen.findByRole("button", { name: "Sessions" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Older chat" }));
    await screen.findByText("prior");

    await userEvent.click(screen.getByRole("button", { name: "New chat" }));
    await waitFor(() => expect(api.createSession).toHaveBeenCalled());
  });
});
