import { EditorView } from "@codemirror/view";
import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useRef } from "react";

import { LIVE_DEBOUNCE_MS, type LiveSource, useLiveSource } from "./use-live-source";

function Probe({ view, onState }: { view: EditorView; onState: (live: LiveSource) => void }) {
  const snapshots = useRef(new Map<string, string>());
  const live = useLiveSource(view, "main", snapshots);
  onState(live);
  return <p data-testid="text">{live.text ?? "none"}</p>;
}

describe("useLiveSource", () => {
  let view: EditorView;

  beforeEach(() => {
    vi.useFakeTimers();
    view = new EditorView({ doc: "", parent: document.body });
  });

  afterEach(() => {
    view.destroy();
    vi.useRealTimers();
  });

  it("settles the open file's text 300 ms after the last change", () => {
    const seen: LiveSource[] = [];
    render(<Probe view={view} onState={(live) => seen.push(live)} />);
    act(() => {
      view.dispatch({ changes: { from: 0, insert: "\\section{New}" } });
    });
    act(() => {
      vi.advanceTimersByTime(LIVE_DEBOUNCE_MS - 1);
    });
    expect(screen.getByTestId("text")).toHaveTextContent("none");
    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(screen.getByTestId("text")).toHaveTextContent("\\section{New}");
  });

  it("follows the cursor line at once", () => {
    const seen: LiveSource[] = [];
    render(<Probe view={view} onState={(live) => seen.push(live)} />);
    act(() => {
      view.dispatch({ changes: { from: 0, insert: "a\nb\nc" }, selection: { anchor: 2 } });
    });
    expect(seen.at(-1)?.line).toBe(2);
  });
});
