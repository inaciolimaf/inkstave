import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/utils";

import { AgentPanel } from "./AgentPanel";
import { SEND_AFTER_KEY } from "./voice/preferences";
import type { RecognizerOptions } from "./voice/speech";

const api = vi.hoisted(() => ({
  listSessions: vi.fn(),
  createSession: vi.fn(),
  getSession: vi.fn(),
  startRun: vi.fn(),
  stopRun: vi.fn(),
  runEventsUrl: vi.fn(() => "http://x/events"),
}));
vi.mock("./api", () => api);

/** The browser's recognizer, replaced: each test drives its events. */
const speech = vi.hoisted(() => {
  class FakeRecognizer {
    static last: FakeRecognizer | null = null;
    start = vi.fn();
    stop = vi.fn();
    abort = vi.fn();
    constructor(public options: RecognizerOptions) {
      FakeRecognizer.last = this;
    }
  }
  return { FakeRecognizer };
});
vi.mock("./voice/speech", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./voice/speech")>()),
  speechSupported: () => true,
  canProcessLocally: async () => true,
  createRecognizer: (options: RecognizerOptions) => new speech.FakeRecognizer(options),
}));

function recognizer(): InstanceType<typeof speech.FakeRecognizer> {
  if (!speech.FakeRecognizer.last) throw new Error("dictation has not started");
  return speech.FakeRecognizer.last;
}

function renderPanel(open = true) {
  return renderWithProviders(
    <AgentPanel projectId="p1" open={open} onOpenChange={vi.fn()} onReviewProposal={vi.fn()} />,
  );
}

beforeEach(() => {
  localStorage.clear();
  speech.FakeRecognizer.last = null;
  vi.stubGlobal(
    "EventSource",
    class {
      addEventListener() {}
      close() {}
    },
  );
  api.listSessions.mockResolvedValue([]);
  api.createSession.mockResolvedValue({ id: "s1", projectId: "p1", title: null, runState: "idle" });
  api.startRun.mockResolvedValue({ runId: "r1", streamUrl: "http://x/events" });
  api.stopRun.mockResolvedValue(undefined);
});
afterEach(() => vi.unstubAllGlobals());

async function startDictation() {
  await userEvent.click(await screen.findByRole("button", { name: "Dictate" }));
  await waitFor(() => expect(speech.FakeRecognizer.last).not.toBeNull());
}

describe("AgentPanel dictation", () => {
  it("puts dictated words in the box and sends nothing (AC2, rule: no unchosen send)", async () => {
    renderPanel();
    await startDictation();
    act(() => recognizer().options.onInterim("troque o título"));
    expect(screen.getByText("troque o título")).toBeInTheDocument();

    act(() => recognizer().options.onFinal("troque o título da seção 2 para Métodos"));
    expect(screen.getByLabelText("Message the agent")).toHaveValue("troque o título da seção 2 para Métodos");
    expect(api.startRun).not.toHaveBeenCalled();
  });

  it("keeps typed text and adds the dictated words after it", async () => {
    renderPanel();
    await userEvent.type(await screen.findByLabelText("Message the agent"), "Rascunho");
    await startDictation();
    act(() => recognizer().options.onFinal("extra"));
    expect(screen.getByLabelText("Message the agent")).toHaveValue("Rascunho extra");
  });

  it("Escape while listening drops what this session put in the box", async () => {
    renderPanel();
    const composer = await screen.findByLabelText("Message the agent");
    await userEvent.type(composer, "Rascunho");
    await startDictation();
    act(() => recognizer().options.onFinal("extra"));

    composer.focus();
    await userEvent.keyboard("{Escape}");
    expect(recognizer().abort).toHaveBeenCalled();
    expect(composer).toHaveValue("Rascunho");
    expect(screen.getByRole("dialog")).toBeVisible();
  });

  it("sends the transcript when the recognition ends, if send-after is on", async () => {
    localStorage.setItem(SEND_AFTER_KEY, "1");
    renderPanel();
    await startDictation();
    act(() => recognizer().options.onFinal("Métodos"));
    act(() => recognizer().options.onEnd());
    await waitFor(() => expect(api.startRun).toHaveBeenCalled());
    expect(JSON.stringify(api.startRun.mock.calls[0])).toContain("Métodos");
  });

  it("shows a blocked microphone in plain words and returns to idle", async () => {
    renderPanel();
    await startDictation();
    act(() => {
      recognizer().options.onError("not-allowed");
      recognizer().options.onEnd();
    });
    expect(screen.getByRole("alert")).toHaveTextContent("Microphone access was blocked.");
    expect(screen.getByRole("button", { name: "Dictate" })).toHaveAttribute("aria-pressed", "false");
  });

  it("stops recognition when the panel folds (AC5)", async () => {
    const { rerender } = renderPanel();
    await startDictation();
    rerender(<AgentPanel projectId="p1" open={false} onOpenChange={vi.fn()} onReviewProposal={vi.fn()} />);
    expect(recognizer().abort).toHaveBeenCalled();
  });
});
