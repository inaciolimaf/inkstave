import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, renderHook, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { HistoryLabels } from "./HistoryLabels";
import type { VersionsPage } from "./types";
import { useHistoryMutations, versionsKey } from "./useHistory";

const api = vi.hoisted(() => ({ createLabel: vi.fn() }));
vi.mock("./api", () => ({
  createLabel: (...a: unknown[]) => api.createLabel(...a),
  deleteLabel: vi.fn(),
  restoreVersion: vi.fn(),
  listVersions: vi.fn(),
  getDiff: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

afterEach(() => vi.clearAllMocks());

const LABELS = [{ id: "l1", name: "submitted" }];

describe("HistoryLabels", () => {
  it("renders label badges", () => {
    render(
      <HistoryLabels
        version={3}
        labels={LABELS}
        canWrite={false}
        onAdd={vi.fn()}
        onDelete={vi.fn()}
      />,
    );
    expect(screen.getByText("submitted")).toBeInTheDocument();
  });

  it("hides add/delete controls for viewers (AC6)", () => {
    render(
      <HistoryLabels
        version={3}
        labels={LABELS}
        canWrite={false}
        onAdd={vi.fn()}
        onDelete={vi.fn()}
      />,
    );
    expect(screen.queryByLabelText("Add label to version 3")).toBeNull();
    expect(screen.queryByLabelText("Remove label submitted")).toBeNull();
  });

  it("lets an editor add a label (AC6)", async () => {
    const onAdd = vi.fn();
    render(<HistoryLabels version={3} labels={[]} canWrite onAdd={onAdd} onDelete={vi.fn()} />);
    await userEvent.click(screen.getByLabelText("Add label to version 3"));
    await userEvent.type(screen.getByLabelText("Label name"), "final");
    await userEvent.click(screen.getByRole("button", { name: "Add" }));
    expect(onAdd).toHaveBeenCalledWith(3, "final");
  });

  it("lets an editor delete a label (AC6)", async () => {
    const onDelete = vi.fn();
    render(
      <HistoryLabels version={3} labels={LABELS} canWrite onAdd={vi.fn()} onDelete={onDelete} />,
    );
    await userEvent.click(screen.getByLabelText("Remove label submitted"));
    expect(onDelete).toHaveBeenCalledWith("l1");
  });
});

describe("addLabel optimistic update (AC6 / issue 151)", () => {
  const PROJECT = "p1";
  const DOC = "d1";

  function makeWrapper(qc: QueryClient) {
    return function Wrapper({ children }: { children: ReactNode }) {
      return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
    };
  }

  function seedVersions(qc: QueryClient) {
    const page: VersionsPage = {
      docId: DOC,
      currentVersion: 3,
      versions: [{ version: 3, timestamp: "t", author: null, opCount: 1, size: 1, labels: [] }],
      hasMore: false,
      nextBefore: null,
    };
    qc.setQueryData(versionsKey(PROJECT, DOC), { pages: [page], pageParams: [null] });
  }

  function labelsForVersion(qc: QueryClient, version: number): string[] {
    const data = qc.getQueryData<{ pages: VersionsPage[] }>(versionsKey(PROJECT, DOC));
    const v = data?.pages.flatMap((p) => p.versions).find((x) => x.version === version);
    return (v?.labels ?? []).map((l) => l.name);
  }

  it("writes the badge optimistically before the mutation resolves", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    seedVersions(qc);
    let resolveCreate: ((v: unknown) => void) | undefined;
    api.createLabel.mockReturnValue(new Promise((res) => (resolveCreate = res)));

    const { result } = renderHook(() => useHistoryMutations(PROJECT, DOC), {
      wrapper: makeWrapper(qc),
    });

    result.current.addLabel.mutate({ version: 3, name: "final" });

    // Optimistic badge present before the server promise resolves.
    await waitFor(() => expect(labelsForVersion(qc, 3)).toContain("final"));

    resolveCreate?.({ id: "real", name: "final", version: 3 });
  });

  it("rolls back and toasts on error", async () => {
    const { toast } = await import("sonner");
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    seedVersions(qc);
    api.createLabel.mockRejectedValue(new Error("nope"));

    const { result } = renderHook(() => useHistoryMutations(PROJECT, DOC), {
      wrapper: makeWrapper(qc),
    });

    result.current.addLabel.mutate({ version: 3, name: "final" });

    await waitFor(() => expect(result.current.addLabel.isError).toBe(true));
    expect(labelsForVersion(qc, 3)).not.toContain("final");
    expect(toast.error).toHaveBeenCalled();
  });
});
