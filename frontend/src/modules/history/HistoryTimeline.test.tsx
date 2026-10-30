import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/utils";

import { HistoryTimeline } from "./HistoryTimeline";
import type { Version, VersionsPage } from "./types";

const api = vi.hoisted(() => ({
  listVersions: vi.fn(),
  getDiff: vi.fn(),
  createLabel: vi.fn(),
  deleteLabel: vi.fn(),
  restoreVersion: vi.fn(),
}));
vi.mock("./api", () => api);

afterEach(() => vi.clearAllMocks());

function v(version: number, over: Partial<Version> = {}): Version {
  return {
    version,
    timestamp: "2026-06-10T08:00:00.000Z",
    author: { id: "u1", name: "Ada Lovelace", email: "ada@x.com" },
    opCount: 2,
    size: 100,
    labels: [],
    ...over,
  };
}

function page(versions: Version[], over: Partial<VersionsPage> = {}): VersionsPage {
  return {
    docId: "d1",
    currentVersion: versions[0]?.version ?? 0,
    versions,
    hasMore: false,
    nextBefore: null,
    ...over,
  };
}

function render(over: Record<string, unknown> = {}) {
  return renderWithProviders(
    <HistoryTimeline
      projectId="p1"
      docId="d1"
      primary={null}
      compare={null}
      canWrite
      onSelect={vi.fn()}
      onAddLabel={vi.fn()}
      onDeleteLabel={vi.fn()}
      {...over}
    />,
  );
}

describe("HistoryTimeline", () => {
  it("renders versions with author + a relative timestamp (AC1, AC3)", async () => {
    api.listVersions.mockResolvedValue(page([v(3), v(2)], { hasMore: false }));
    render();
    expect(await screen.findByText("v3 · 2 changes")).toBeInTheDocument();
    expect(screen.getAllByText("Ada Lovelace")).toHaveLength(2);
  });

  it("paginates with Load more and hides it at the end (AC2)", async () => {
    api.listVersions.mockImplementation((_p: string, _d: string, opts: { before?: number }) =>
      Promise.resolve(
        opts.before === undefined
          ? page([v(3), v(2)], { hasMore: true, nextBefore: 2 })
          : page([v(1)], { hasMore: false }),
      ),
    );
    render();
    const loadMore = await screen.findByRole("button", { name: "Load more" });
    await userEvent.click(loadMore);
    await waitFor(() => expect(screen.getByText("v1 · 2 changes")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Load more" })).toBeNull();
    expect(api.listVersions).toHaveBeenCalledWith("p1", "d1", { before: 2, limit: 50 });
  });

  it("shows an empty state with no versions (spec 64 AC4)", async () => {
    api.listVersions.mockResolvedValue(page([], { currentVersion: 0 }));
    render();
    expect(await screen.findByText("No history yet.")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows the error state with Retry on load failure (spec 64 AC5)", async () => {
    api.listVersions.mockRejectedValue(new Error("boom"));
    render();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Couldn’t load history.");
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("selects a version on click", async () => {
    api.listVersions.mockResolvedValue(page([v(2)]));
    const onSelect = vi.fn();
    render({ onSelect });
    await userEvent.click(await screen.findByText("Ada Lovelace"));
    expect(onSelect).toHaveBeenCalledWith(2, false);
  });

  it("makes version rows keyboard-focusable and activatable (AC10)", async () => {
    api.listVersions.mockResolvedValue(page([v(2)]));
    const onSelect = vi.fn();
    render({ onSelect });
    await screen.findByText("Ada Lovelace");

    const rows = screen.getAllByRole("button", { name: /Ada Lovelace/ });
    const row = rows.find((el) => el.getAttribute("tabindex") === "0")!;
    expect(row).toBeDefined();
    expect(row).toHaveAttribute("tabindex", "0"); // reachable via the tab order

    // Tab reaches the row, and Enter / Space activate it (keyboard parity w/ click).
    await userEvent.tab();
    expect(row).toHaveFocus();
    await userEvent.keyboard("{Enter}");
    expect(onSelect).toHaveBeenCalledWith(2, false);
    await userEvent.keyboard(" ");
    expect(onSelect).toHaveBeenCalledTimes(2);
  });
});
