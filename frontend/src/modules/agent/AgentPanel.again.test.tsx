/**
 * "Do it again" lifecycle tests for the agent panel: several runs in one chat, a cancel
 * or an error followed by a send, and a reload in the middle of a run. Each run's
 * events restart at seq 0, so the second run must still stream in full.
 */
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
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
    (this.listeners[event.type as string] ?? []).forEach((fn) => fn({ data: JSON.stringify(event) }));
  }
}

const OLD = { id: "old", projectId: "p1", title: "Older chat", runState: "idle" };

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
  api.listSessions.mockResolvedValue([]);
  api.createSession.mockResolvedValue({ id: "s1", projectId: "p1", title: null, runState: "idle" });
  api.startRun.mockResolvedValue({ runId: "r1", streamUrl: "http://x/events" });
  api.stopRun.mockResolvedValue(undefined);
});
afterEach(() => vi.unstubAllGlobals());

function renderPanel() {
  return renderWithProviders(
    <AgentPanel projectId="p1" open onOpenChange={vi.fn()} onReviewProposal={vi.fn()} />,
  );
}

/** The transcript only: the status line repeats the newest text for screen readers. */
const transcript = () => within(screen.getByRole("log"));

async function sendText(text: string, sessionId = "s1") {
  const composer = await screen.findByLabelText("Message the agent");
  await waitFor(() => expect(composer).not.toBeDisabled());
  fireEvent.change(composer, { target: { value: text } });
  await userEvent.click(screen.getByLabelText("Send message"));
  await waitFor(() => expect(api.startRun).toHaveBeenLastCalledWith("p1", sessionId, text));
  await waitFor(() => expect(FakeEventSource.instances.at(-1)?.listeners.token).toBeDefined());
  return FakeEventSource.instances.at(-1)!;
}

/** The run has ended: no Stop button, and the composer takes a new message. */
async function expectIdle() {
  await waitFor(() => expect(screen.queryByRole("button", { name: "Stop the run" })).toBeNull());
  await waitFor(() => expect(screen.getByLabelText("Message the agent")).not.toBeDisabled());
}

describe("AgentPanel, do it again", () => {
  it("runs three times in one chat, each streaming in full with overlapping seq numbers", async () => {
    renderPanel();
    const answers = ["Alpha one", "Beta two", "Gamma three"];
    for (const [i, answer] of answers.entries()) {
      const es = await sendText(`question ${i}`);
      const [first, second] = answer.split(" ", 2).map((w) => `${w} `);
      es.emit({ type: "token", seq: 0, text: first });
      es.emit({ type: "token", seq: 1, text: second.trim() });
      es.emit({ type: "done", seq: 2, final_text: answer, usage: {}, iterations: 1 });
      await waitFor(() => expect(transcript().getByText(answer)).toBeInTheDocument());
      await expectIdle();
    }
    expect(FakeEventSource.instances).toHaveLength(3);
    expect(FakeEventSource.instances.every((es) => es.closed)).toBe(true);
  });

  it("cancels a run, then streams the next one in full", async () => {
    renderPanel();
    const first = await sendText("long task");
    first.emit({ type: "token", seq: 0, text: "Working" });
    await userEvent.click(await screen.findByRole("button", { name: "Stop the run" }));
    first.emit({ type: "error", seq: 1, code: "cancelled", message: "Run cancelled." });
    await transcript().findByText("Run cancelled");
    await expectIdle();

    api.startRun.mockResolvedValue({ runId: "r2", streamUrl: "http://x/events" });
    const second = await sendText("short task");
    second.emit({ type: "token", seq: 0, text: "Fresh " });
    second.emit({ type: "token", seq: 1, text: "answer" });
    await transcript().findByText("Fresh answer");
    second.emit({ type: "done", seq: 2, final_text: "Fresh answer", usage: {}, iterations: 1 });
    await expectIdle();
  });

  it("recovers after an error run and the spinner ends on the error", async () => {
    renderPanel();
    const failing = await sendText("first try");
    failing.emit({ type: "error", seq: 0, code: "llm_error", message: "upstream failed" });
    await waitFor(() =>
      expect(transcript().getByText("The AI service is temporarily unavailable.")).toBeInTheDocument(),
    );
    await expectIdle();

    const ok = await sendText("second try");
    ok.emit({ type: "token", seq: 0, text: "It worked" });
    ok.emit({ type: "done", seq: 1, final_text: "It worked", usage: {}, iterations: 1 });
    await transcript().findByText("It worked");
    await expectIdle();
  });

  it("reloads in the middle of a run, then continues in the same chat", async () => {
    api.listSessions.mockResolvedValue([OLD]);
    api.getSession.mockResolvedValue({
      session: OLD,
      messages: [
        { id: "m1", seq: 0, role: "user", content: "earlier question", tool_calls: null, tool_call_id: null },
      ],
      diffs: [],
      file_ops: [],
    });
    const { unmount } = renderPanel();
    const mid = await sendText("mid run");
    mid.emit({ type: "token", seq: 0, text: "Half done" });
    await transcript().findByText("Half done");

    // Reload: the page is rebuilt, and the run's stream is gone with it.
    unmount();
    expect(mid.closed).toBe(true);
    renderPanel();
    await userEvent.click(await screen.findByRole("button", { name: "Sessions" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Older chat" }));
    await transcript().findByText("earlier question");
    expect(transcript().queryByText("Half done")).toBeNull();
    await expectIdle();

    const after = await sendText("continue", "old");
    after.emit({ type: "token", seq: 0, text: "Continued" });
    after.emit({ type: "done", seq: 1, final_text: "Continued", usage: {}, iterations: 1 });
    await transcript().findByText("Continued");
    await expectIdle();
  });

  it("keeps a proposal next to its turn after a reload, and a later turn stays below it", async () => {
    api.listSessions.mockResolvedValue([OLD]);
    api.getSession.mockResolvedValue({
      session: OLD,
      messages: [
        { id: "m1", seq: 0, role: "user", content: "first ask", tool_calls: null, tool_call_id: null },
        {
          id: "m2",
          seq: 1,
          role: "assistant",
          content: "First answer",
          tool_calls: null,
          tool_call_id: null,
        },
        { id: "m3", seq: 2, role: "user", content: "second ask", tool_calls: null, tool_call_id: null },
        {
          id: "m4",
          seq: 3,
          role: "assistant",
          content: "Second answer",
          tool_calls: null,
          tool_call_id: null,
        },
      ],
      diffs: [
        {
          id: "d1",
          message_id: "m2",
          doc_id: "doc",
          path: "main.tex",
          status: "proposed",
          stats: { hunk_count: 1 },
        },
      ],
      file_ops: [],
    });
    renderPanel();
    await userEvent.click(await screen.findByRole("button", { name: "Sessions" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Older chat" }));

    const review = await transcript().findByRole("button", { name: /Review changes/ });
    const first = transcript().getByText("First answer");
    const second = transcript().getByText("Second answer");
    expect(first.compareDocumentPosition(review) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(review.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});
