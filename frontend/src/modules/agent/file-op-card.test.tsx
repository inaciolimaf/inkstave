import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api-client";

import * as api from "./api";
import { FileOpCard } from "./file-op-card";
import type { FileOp } from "./types";

vi.mock("./api", async (original) => ({
  ...(await original<typeof import("./api")>()),
  decideFileOp: vi.fn(),
  fetchFileOpContent: vi.fn(),
}));

const decide = vi.mocked(api.decideFileOp);

const base: FileOp = {
  opId: "op1",
  opKind: "create",
  entityType: "doc",
  path: "chapters/intro.tex",
  newPath: null,
  affectedPaths: [],
  status: "proposed",
  rationale: null,
};

function renderCard(op: FileOp) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidate = vi.spyOn(client, "invalidateQueries");
  render(
    <QueryClientProvider client={client}>
      <FileOpCard projectId="p1" sessionId="s1" op={op} />
    </QueryClientProvider>,
  );
  return { invalidate };
}

describe("FileOpCard", () => {
  beforeEach(() => {
    decide.mockReset();
  });

  it("applies a new file and refreshes the tree", async () => {
    decide.mockResolvedValue({ ...base, status: "applied" });
    const { invalidate } = renderCard(base);
    expect(screen.getByText("Create file")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Apply" }));

    expect(decide).toHaveBeenCalledWith("p1", "s1", "op1", "apply");
    await screen.findByText("Applied");
    expect(invalidate).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: "Apply" })).not.toBeInTheDocument();
  });

  it("does nothing to the tree when rejected", async () => {
    decide.mockResolvedValue({ ...base, status: "rejected" });
    const { invalidate } = renderCard(base);
    await userEvent.click(screen.getByRole("button", { name: "Reject" }));
    await screen.findByText("Rejected");
    expect(decide).toHaveBeenCalledWith("p1", "s1", "op1", "reject");
    expect(invalidate).not.toHaveBeenCalled();
  });

  it("asks before deleting and says what else goes", async () => {
    decide.mockResolvedValue({ ...base, status: "applied" });
    renderCard({ ...base, opKind: "delete", path: "old", affectedPaths: ["old", "old/a.tex"] });
    expect(screen.getByText("Also deletes 1 item inside it")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(decide).not.toHaveBeenCalled();
    await userEvent.click(await screen.findByRole("button", { name: "Delete" }));
    await waitFor(() => expect(decide).toHaveBeenCalledWith("p1", "s1", "op1", "apply"));
  });

  it("shows why the server refused and keeps the proposal open", async () => {
    decide.mockRejectedValue(new ApiError(409, "The project changed since this was proposed."));
    renderCard({ ...base, opKind: "move", newPath: "b.tex" });
    await userEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The project changed");
    expect(screen.getByRole("button", { name: "Apply" })).toBeEnabled();
  });

  it("loads a new document's content only when asked", async () => {
    vi.mocked(api.fetchFileOpContent).mockResolvedValue("\\section{Intro}");
    renderCard(base);
    expect(api.fetchFileOpContent).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Show content" }));
    expect(await screen.findByText("\\section{Intro}")).toBeInTheDocument();
  });

  it("shows a decided proposal without its buttons", () => {
    renderCard({ ...base, status: "applied" });
    expect(screen.getByRole("status")).toHaveTextContent("Applied");
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
