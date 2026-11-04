import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { DictationApi } from "./use-dictation";
import { DictateButton } from "./mic-button";
import { DictationStatus } from "./dictation-status";

function fakeDictation(overrides: Partial<DictationApi> = {}): DictationApi {
  return {
    supported: true,
    state: "idle",
    interim: "",
    error: null,
    lang: "en-US",
    setLang: vi.fn(),
    sendAfter: false,
    setSendAfter: vi.fn(),
    toggle: vi.fn(),
    stop: vi.fn(),
    cancel: vi.fn(),
    answerConsent: vi.fn(),
    ...overrides,
  };
}

describe("DictateButton", () => {
  it("is absent where the browser has no speech recognition (AC1)", () => {
    const { container } = render(
      <DictateButton dictation={fakeDictation({ supported: false })} disabled={false} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("labels the press state and toggles dictation on click", async () => {
    const dictation = fakeDictation();
    const { rerender } = render(<DictateButton dictation={dictation} disabled={false} />);
    const mic = screen.getByRole("button", { name: "Dictate" });
    expect(mic).toHaveAttribute("aria-pressed", "false");
    await userEvent.click(mic);
    expect(dictation.toggle).toHaveBeenCalled();

    rerender(<DictateButton dictation={fakeDictation({ state: "listening" })} disabled={false} />);
    expect(screen.getByRole("button", { name: "Stop dictating" })).toHaveAttribute("aria-pressed", "true");
  });

  it("is disabled while a run is in progress, like the send button", () => {
    render(<DictateButton dictation={fakeDictation()} disabled />);
    expect(screen.getByRole("button", { name: "Dictate" })).toBeDisabled();
  });

  it("switches the recognition language from its menu", async () => {
    const dictation = fakeDictation();
    render(<DictateButton dictation={dictation} disabled={false} />);
    await userEvent.click(screen.getByRole("button", { name: "Dictation options" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Português (Brasil)" }));
    expect(dictation.setLang).toHaveBeenCalledWith("pt-BR");
  });

  it("turns send-after-dictation on from the same menu", async () => {
    const dictation = fakeDictation();
    render(<DictateButton dictation={dictation} disabled={false} />);
    await userEvent.click(screen.getByRole("button", { name: "Dictation options" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Send after dictation" }));
    expect(dictation.setSendAfter).toHaveBeenCalledWith(true);
  });
});

describe("DictationStatus", () => {
  it("asks for consent with Continue and Cancel, and reports the answer", async () => {
    const dictation = fakeDictation({ state: "asking-consent" });
    render(<DictationStatus dictation={dictation} />);
    expect(screen.getByText(/Inkstave never receives the audio/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(dictation.answerConsent).toHaveBeenLastCalledWith(false);
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(dictation.answerConsent).toHaveBeenLastCalledWith(true);
  });

  it("shows the words being heard in a muted line while listening", () => {
    render(<DictationStatus dictation={fakeDictation({ state: "listening", interim: "troque o" })} />);
    expect(screen.getByText("Listening…")).toBeInTheDocument();
    expect(screen.getByText("troque o")).toHaveClass("italic");
  });

  it("explains a blocked microphone in plain words, never as a dialog", () => {
    render(<DictationStatus dictation={fakeDictation({ error: "not-allowed" })} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Microphone access was blocked.");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("renders nothing when idle without an error", () => {
    const { container } = render(<DictationStatus dictation={fakeDictation()} />);
    expect(container).toBeEmptyDOMElement();
  });
});
