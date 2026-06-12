import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest";

import { UploadError, uploadFile } from "./api";
import { FileTreePanel } from "./file-tree-panel";

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
vi.mock("./api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api")>();
  return { ...actual, uploadFile: vi.fn() };
});

const ROOT = {
  id: "root",
  project_id: "p",
  parent_id: null,
  type: "folder",
  name: "root",
  is_root: true,
  path: "",
  children: [],
};

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(JSON.stringify({ root: ROOT }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
    ),
  );
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("FileTreePanel upload", () => {
  it("uploads a binary with progress and shows it complete", async () => {
    (uploadFile as Mock).mockImplementation(
      async (_pid: string, input: { file: File; onProgress?: (n: number) => void }) => {
        input.onProgress?.(50);
        input.onProgress?.(100);
        return {
          id: "f1",
          name: input.file.name,
          type: "file",
          parentId: "root",
          isRoot: false,
          path: "",
        };
      },
    );

    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    const { container } = render(
      <QueryClientProvider client={qc}>
        <FileTreePanel projectId="p" selectedId={null} onSelectEntity={vi.fn()} />
      </QueryClientProvider>,
    );

    await screen.findByRole("button", { name: "Upload file" });
    await userEvent.click(screen.getByRole("button", { name: "Upload file" }));

    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File([new Uint8Array([1, 2, 3])], "logo.png", { type: "image/png" });
    fireEvent.change(input, { target: { files: [file] } });

    expect(await screen.findByText("logo.png")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Done")).toBeInTheDocument());
    expect(uploadFile).toHaveBeenCalledWith(
      "p",
      expect.objectContaining({ file, parentId: "root" }),
    );
    expect(toast.success).toHaveBeenCalledWith("Uploaded logo.png");
  });

  it("surfaces a 409 name_conflict as a conflict prompt", async () => {
    (uploadFile as Mock).mockImplementation(async () => {
      throw new UploadError(409, "name_conflict");
    });

    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    const { container } = render(
      <QueryClientProvider client={qc}>
        <FileTreePanel projectId="p" selectedId={null} onSelectEntity={vi.fn()} />
      </QueryClientProvider>,
    );

    await screen.findByRole("button", { name: "Upload file" });
    await userEvent.click(screen.getByRole("button", { name: "Upload file" }));

    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File([new Uint8Array([1, 2, 3])], "logo.png", { type: "image/png" });
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => expect(uploadFile).toHaveBeenCalled());
    // The 409/name_conflict surfaces as the Replace/Cancel conflict prompt (spec 17 §5.3.5),
    // not a success — the user is asked how to resolve the clash.
    expect(await screen.findByRole("alertdialog")).toHaveTextContent(/already exists/i);
    expect(screen.getByRole("button", { name: "Replace" })).toBeInTheDocument();
    expect(toast.success).not.toHaveBeenCalled();
  });
});
