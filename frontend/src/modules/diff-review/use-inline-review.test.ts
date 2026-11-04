/** Opening a proposal's review from its card (spec 110), including when the editor must switch documents first. */
import { EditorState } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchProposal } from "./api";
import { inlineReviewExtension, inlineReviewField } from "./inline-review-extension";
import type { DiffProposal, DocumentBridge } from "./types";
import { type UseInlineReviewOptions, useInlineReview } from "./use-inline-review";

vi.mock("sonner", () => ({ toast: { error: vi.fn(), message: vi.fn() } }));
vi.mock("./api", () => ({ fetchProposal: vi.fn(), recordDecision: vi.fn() }));

const PROPOSAL: DiffProposal = {
  id: "d1",
  projectId: "p1",
  sessionId: "s1",
  status: "proposed",
  createdAt: "2026-01-01T00:00:00Z",
  files: [
    {
      path: "b.tex",
      baseVersion: "v1",
      docId: "doc-b",
      hunks: [
        {
          id: "h1",
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

const views: EditorView[] = [];
afterEach(() => {
  views.splice(0).forEach((v) => v.destroy());
  vi.mocked(fetchProposal).mockReset();
});

function editor(doc: string): EditorView {
  const view = new EditorView({
    state: EditorState.create({ doc, extensions: [inlineReviewExtension] }),
    parent: document.body.appendChild(document.createElement("div")),
  });
  views.push(view);
  return view;
}

function options(view: EditorView | null, openPath: string): UseInlineReviewOptions {
  const bridge: DocumentBridge = {
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
    onDecided: vi.fn(),
  };
}

const REF = { sessionId: "s1", proposalId: "d1", path: "b.tex" };

describe("useInlineReview", () => {
  it("starts on the proposal's editor with one click when another document was open", async () => {
    vi.mocked(fetchProposal).mockResolvedValue(PROPOSAL);
    const viewA = editor("other");
    const { result, rerender } = renderHook((props: UseInlineReviewOptions) => useInlineReview(props), {
      initialProps: options(viewA, "a.tex"),
    });

    act(() => result.current.open(REF));
    // The open path switches first, while a.tex's editor is still mounted; then it goes and b.tex's mounts.
    rerender(options(viewA, "b.tex"));
    rerender(options(null, "b.tex"));
    const viewB = editor("a\nb\nc");
    rerender(options(viewB, "b.tex"));

    await waitFor(() => expect(viewB.state.field(inlineReviewField)).not.toBeNull());
    expect(viewA.state.field(inlineReviewField)).toBeNull();
    expect(fetchProposal).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(result.current.bar).not.toBeNull());
  });

  it("starts at once when the proposal's document is already open", async () => {
    vi.mocked(fetchProposal).mockResolvedValue(PROPOSAL);
    const viewB = editor("a\nb\nc");
    const { result } = renderHook((props: UseInlineReviewOptions) => useInlineReview(props), {
      initialProps: options(viewB, "b.tex"),
    });

    act(() => result.current.open(REF));

    await waitFor(() => expect(viewB.state.field(inlineReviewField)).not.toBeNull());
  });
});
