import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/utils";

import { HistoryDiffView } from "./HistoryDiffView";
import type { DiffResult } from "./types";

// Pull in the real `getDiff` (which maps a backend 413 → tooLarge) so the
// too-large case can exercise the actual production code path rather than a
// hand-rolled resolved value that would mask the bug.
const { getDiff: realGetDiff } = await vi.importActual<typeof import("./api")>("./api");

const api = vi.hoisted(() => ({
  listVersions: vi.fn(),
  getDiff: vi.fn(),
  createLabel: vi.fn(),
  deleteLabel: vi.fn(),
  restoreVersion: vi.fn(),
}));
vi.mock("./api", () => api);

afterEach(() => {
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

interface FetchResponse {
  ok: boolean;
  status: number;
  statusText: string;
  json: () => Promise<unknown>;
  text: () => Promise<string>;
}

function stubFetch(status: number, body: unknown) {
  const text = JSON.stringify(body);
  const res: FetchResponse = {
    ok: status >= 200 && status < 300,
    status,
    statusText: "",
    json: async () => JSON.parse(text),
    text: async () => text,
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => res),
  );
}

function diff(over: Partial<DiffResult> = {}): DiffResult {
  return { from: 1, to: "current", binary: false, tooLarge: false, hunks: [], ...over };
}

function render(from: number | null = 1, to: number | "current" | null = "current") {
  return renderWithProviders(<HistoryDiffView projectId="p1" docId="d1" from={from} to={to} />);
}

describe("HistoryDiffView", () => {
  it("renders added/removed/context segments with markers (AC4, AC10)", async () => {
    api.getDiff.mockResolvedValue(
      diff({
        hunks: [
          {
            oldStart: 1,
            oldLines: 2,
            newStart: 1,
            newLines: 2,
            segments: [
              { type: "context", value: "\\section{Intro}\n" },
              { type: "removed", value: "old line\n" },
              { type: "added", value: "new line\n" },
            ],
          },
        ],
      }),
    );
    render();
    expect(await screen.findByText("new line")).toBeInTheDocument();
    const removed = document.querySelector('[data-type="removed"]');
    const added = document.querySelector('[data-type="added"]');
    expect(removed?.textContent).toContain("-"); // marker, not colour-only
    expect(added?.textContent).toContain("+");
  });

  it("shows the binary fallback (AC5)", async () => {
    api.getDiff.mockResolvedValue(diff({ binary: true }));
    render();
    expect(await screen.findByText("This document has no text diff.")).toBeInTheDocument();
  });

  it("shows the too-large fallback, not the generic error, on a backend 413 (spec 61 AC4, spec 71 AC1)", async () => {
    // The backend signals "too large" with HTTP 413 + `too_large: true`; the
    // real `getDiff` must turn that rejection into a tooLarge result so the view
    // renders the fallback (not the generic error branch). Driving the *real*
    // `getDiff` here proves the production code path, unlike a resolved stub.
    stubFetch(413, { from: 1, to: "current", binary: false, too_large: true, hunks: [] });
    api.getDiff.mockImplementation(realGetDiff);
    render();
    expect(await screen.findByText("This version is too large to diff.")).toBeInTheDocument();
    expect(screen.queryByText("Couldn’t load the diff.")).not.toBeInTheDocument();
  });

  it("prompts to select a version when none is chosen", () => {
    render(null, null);
    expect(screen.getByText("Select a version to see what changed.")).toBeInTheDocument();
    expect(api.getDiff).not.toHaveBeenCalled();
  });
});
