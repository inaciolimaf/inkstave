/** Shared render helpers and fixture builders for DiffReviewDialog tests (spec 47). */
import { vi } from "vitest";

import { renderWithProviders } from "@/test/utils";

import { createYDocBridge } from "./crdt-apply";
import { DiffReviewDialog } from "./DiffReviewDialog";
import type { DiffHunk, DiffProposal, DocumentBridge, LineType } from "./types";

/** Concrete bridge returned by {@link createYDocBridge} — exposes `getText` for assertions. */
type TestBridge = ReturnType<typeof createYDocBridge>;

export function hunk(id: string, oldStart: number, lines: [LineType, string][]): DiffHunk {
  return {
    id,
    header: `@@ -${oldStart} @@`,
    oldStart,
    oldLines: lines.filter(([t]) => t !== "add").length,
    newStart: oldStart,
    newLines: lines.filter(([t]) => t !== "del").length,
    lines: lines.map(([type, text]) => ({ type, text })),
  };
}

export function proposal(): DiffProposal {
  return {
    id: "d1",
    projectId: "p1",
    sessionId: "s1",
    createdAt: "2026-06-11T00:00:00Z",
    files: [
      {
        path: "main.tex",
        docId: "main",
        baseVersion: "3",
        hunks: [
          hunk("h1", 2, [
            ["del", "b"],
            ["add", "B"],
          ]),
          hunk("h2", 4, [
            ["del", "d"],
            ["add", "D"],
          ]),
        ],
      },
    ],
  };
}

export function render<B extends DocumentBridge = TestBridge>(
  bridge: B = createYDocBridge({ "main.tex": "a\nb\nc\nd\n" }) as unknown as B,
  onOpenChange = vi.fn(),
) {
  const ui = renderWithProviders(
    <DiffReviewDialog
      projectId="p1"
      sessionId="s1"
      proposalId="d1"
      bridge={bridge}
      open
      onOpenChange={onOpenChange}
    />,
  );
  return { bridge, ui, onOpenChange };
}
