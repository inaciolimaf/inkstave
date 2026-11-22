/**
 * "Do it again" lifecycle tests for the History panel: select a version, close, reopen; and
 * switch to another document, which must not keep the first document's selection.
 */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/utils";

import { HistoryPanel } from "./HistoryPanel";
import type { Version, VersionsPage } from "./types";

const api = vi.hoisted(() => ({
  listVersions: vi.fn(),
  getDiff: vi.fn(),
  createLabel: vi.fn(),
  deleteLabel: vi.fn(),
  restoreVersion: vi.fn(),
}));
vi.mock("./api", () => api);
vi.mock("@/modules/sharing", () => ({
  usePermissions: () => ({ data: undefined }),
  hasCapability: () => true,
}));

function version(n: number): Version {
  return {
    version: n,
    timestamp: "2026-06-10T08:00:00.000Z",
    author: { id: "u1", name: `Author ${n}`, email: "a@x.com" },
    opCount: 1,
    size: 10,
    labels: [],
  };
}

function page(docId: string, versions: Version[]): VersionsPage {
  return { docId, currentVersion: versions[0].version, versions, hasMore: false, nextBefore: null };
}

const DOCS: Record<string, Version[]> = {
  d1: [version(3), version(2), version(1)],
  d2: [version(9), version(8)],
};

beforeEach(() => {
  api.listVersions.mockImplementation(async (_p: string, docId: string) => page(docId, DOCS[docId]));
  api.getDiff.mockResolvedValue({ from: 1, to: 2, binary: false, tooLarge: false, hunks: [] });
});
afterEach(() => vi.clearAllMocks());

function panel(docId: string, open: boolean, onOpenChange = vi.fn()) {
  return (
    <HistoryPanel projectId="p1" docId={docId} open={open} onOpenChange={onOpenChange} />
  );
}

/** The timeline row for one version; its aria-pressed says whether it is selected. */
async function row(n: number) {
  const list = await screen.findByRole("list", { name: /./ });
  return within(list).getByText(`Author ${n}`).closest('[role="button"]') as HTMLElement;
}

describe("HistoryPanel, do it again", () => {
  it("selects a version, closes, and reopens on the same document with the versions still listed", async () => {
    const onOpenChange = vi.fn();
    const { rerender } = renderWithProviders(panel("d1", true, onOpenChange));
    await userEvent.click(await row(2));
    await waitFor(() => expect(api.getDiff).toHaveBeenCalledWith("p1", "d1", 1, 2));
    expect(await row(2)).toHaveAttribute("aria-pressed", "true");

    rerender(panel("d1", false, onOpenChange));
    rerender(panel("d1", true, onOpenChange));
    expect(await row(3)).toBeInTheDocument();
    expect(await row(1)).toBeInTheDocument();
    expect(api.listVersions).toHaveBeenCalledWith("p1", "d1", expect.anything());
  });

  it("opens the second document with no version of the first still selected", async () => {
    const { rerender } = renderWithProviders(panel("d1", true));
    await userEvent.click(await row(2));
    await waitFor(() => expect(api.getDiff).toHaveBeenCalledWith("p1", "d1", 1, 2));
    api.getDiff.mockClear();

    rerender(panel("d2", true));
    expect(await row(9)).toHaveAttribute("aria-pressed", "false");
    expect(await row(8)).toHaveAttribute("aria-pressed", "false");
    expect(screen.queryByRole("button", { name: /restore/i })).toBeNull();
    // No diff may be requested for document two with version numbers of document one.
    await waitFor(() => expect(api.listVersions).toHaveBeenCalledWith("p1", "d2", expect.anything()));
    for (const call of api.getDiff.mock.calls) expect(call[1]).not.toBe("d1");
    expect(api.getDiff.mock.calls.filter((c) => c[1] === "d2")).toHaveLength(0);
  });

  it("switches back to the first document and selects again", async () => {
    const { rerender } = renderWithProviders(panel("d1", true));
    await userEvent.click(await row(2));
    rerender(panel("d2", true));
    rerender(panel("d1", true));
    await userEvent.click(await row(1));
    // The first version has nothing before it, so it is compared with the current text.
    await waitFor(() => expect(api.getDiff).toHaveBeenLastCalledWith("p1", "d1", 1, "current"));
    expect(await row(1)).toHaveAttribute("aria-pressed", "true");
  });
});
