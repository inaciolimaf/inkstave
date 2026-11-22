/**
 * "Do it again" lifecycle tests for the inline review: decide one proposal, open another,
 * reopen the first; and switch documents and come back. Each step must start the review on
 * the editor that is showing the proposal's document, with no second click.
 */
import { EditorState } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { fetchProposal, recordDecision } from "./api";
import { inlineReviewExtension, inlineReviewField } from "./inline-review-extension";
import type { DiffProposal, DocumentBridge } from "./types";
import { type UseInlineReviewOptions, useInlineReview } from "./use-inline-review";

vi.mock("sonner", () => ({ toast: { error: vi.fn(), message: vi.fn() } }));
vi.mock("./api", () => ({ fetchProposal: vi.fn(), recordDecision: vi.fn() }));

function proposal(id: string, status = "proposed"): DiffProposal {
  return {
    id,
    projectId: "p1",
    sessionId: "s1",
    status,
    createdAt: "2026-01-01T00:00:00Z",
    files: [
      {
        path: "b.tex",
        baseVersion: "v1",
        docId: "doc-b",
        hunks: [
          {
            id: `${id}-h1`,
            header: "@@ -2 @@",
            oldStart: 2,
            oldLines: 1,
            newStart: 2,
            newLines: 1,
            lines: [
              { type: "del", text: "b" },
              { type: "add", text: "B" },
            ],
          },
        ],
      },
    ],
  };
}

const views: EditorView[] = [];
beforeEach(() => {
  vi.mocked(recordDecision).mockResolvedValue("accepted");
});
afterEach(() => {
  views.splice(0).forEach((v) => v.destroy());
  vi.mocked(fetchProposal).mockReset();
  vi.mocked(recordDecision).mockReset();
});

function editor(doc: string): EditorView {
  const view = new EditorView({
    state: EditorState.create({ doc, extensions: [inlineReviewExtension] }),
    parent: document.body.appendChild(document.createElement("div")),
  });
  views.push(view);
  return view;
}

function options(view: EditorView | null, openPath: string, onDecided = vi.fn()): UseInlineReviewOptions {
  const bridge = {
    readContent: async () => "a\nb\nc",
    applyContent: async () => undefined,
  } as unknown as DocumentBridge;
  return {
    projectId: "p1",
    bridge,
    view,
    openPath,
    canDecide: true,
    openDocument: () => true,
    onDecided,
  };
}

const ref = (proposalId: string) => ({ sessionId: "s1", proposalId, path: "b.tex" });

describe("useInlineReview, do it again", () => {
  it("decides one proposal, opens another, then reopens the first and finds it decided", async () => {
    const onDecided = vi.fn();
    vi.mocked(fetchProposal).mockImplementation(async (_p, _s, id) => proposal(id));
    const viewB = editor("a\nb\nc");
    const { result } = renderHook((props: UseInlineReviewOptions) => useInlineReview(props), {
      initialProps: options(viewB, "b.tex", onDecided),
    });

    // 1. Open and decide the first proposal.
    act(() => result.current.open(ref("d1")));
    await waitFor(() => expect(viewB.state.field(inlineReviewField)).not.toBeNull());
    await waitFor(() => expect(result.current.bar).not.toBeNull());
    await act(async () => result.current.bar?.onAcceptAll());
    await waitFor(() => expect(onDecided).toHaveBeenCalledWith("d1", "accepted"));
    expect(viewB.state.field(inlineReviewField)).toBeNull();

    // 2. Open another proposal on the same document: it starts at once.
    act(() => result.current.open(ref("d2")));
    await waitFor(() => expect(viewB.state.field(inlineReviewField)?.proposalId).toBe("d2"));

    // 3. Close it, then reopen the first: the server says it is decided, so no review starts.
    await waitFor(() => expect(result.current.bar).not.toBeNull());
    act(() => result.current.bar?.onClose());
    await waitFor(() => expect(viewB.state.field(inlineReviewField)).toBeNull());
    vi.mocked(fetchProposal).mockImplementation(async (_p, _s, id) =>
      proposal(id, id === "d1" ? "accepted" : "proposed"),
    );
    act(() => result.current.open(ref("d1")));
    await waitFor(() => expect(fetchProposal).toHaveBeenCalledTimes(3));
    expect(viewB.state.field(inlineReviewField)).toBeNull();
  });

  it("reopens a proposal that was closed undecided, and starts it at once", async () => {
    vi.mocked(fetchProposal).mockImplementation(async (_p, _s, id) => proposal(id));
    const viewB = editor("a\nb\nc");
    const { result } = renderHook((props: UseInlineReviewOptions) => useInlineReview(props), {
      initialProps: options(viewB, "b.tex"),
    });

    for (let round = 0; round < 2; round++) {
      act(() => result.current.open(ref("d1")));
      await waitFor(() => expect(viewB.state.field(inlineReviewField)?.proposalId).toBe("d1"));
      await waitFor(() => expect(result.current.bar).not.toBeNull());
      act(() => result.current.bar?.onClose());
      await waitFor(() => expect(viewB.state.field(inlineReviewField)).toBeNull());
    }
    expect(fetchProposal).toHaveBeenCalledTimes(2);
  });

  it("switches document and comes back: the review opens on the editor that now shows it", async () => {
    vi.mocked(fetchProposal).mockImplementation(async (_p, _s, id) => proposal(id));
    const viewA = editor("other");
    const { result, rerender } = renderHook((props: UseInlineReviewOptions) => useInlineReview(props), {
      initialProps: options(viewA, "a.tex"),
    });

    // Open b.tex's proposal from a.tex: the review waits for b.tex's editor.
    act(() => result.current.open(ref("d1")));
    rerender(options(viewA, "b.tex"));
    const viewB = editor("a\nb\nc");
    rerender(options(viewB, "b.tex"));
    await waitFor(() => expect(viewB.state.field(inlineReviewField)?.proposalId).toBe("d1"));

    // Leave for a.tex: the review ends with its editor.
    const viewA2 = editor("other");
    // The old editor unmounts with its document, so its review goes with it.
    viewB.destroy();
    rerender(options(viewA2, "a.tex"));
    await waitFor(() => expect(result.current.bar).toBeNull());

    // Come back to b.tex from a.tex with one click.
    act(() => result.current.open(ref("d1")));
    rerender(options(viewA2, "b.tex"));
    const viewB2 = editor("a\nb\nc");
    rerender(options(viewB2, "b.tex"));
    await waitFor(() => expect(viewB2.state.field(inlineReviewField)?.proposalId).toBe("d1"));
    expect(viewA2.state.field(inlineReviewField)).toBeNull();
  });
});
