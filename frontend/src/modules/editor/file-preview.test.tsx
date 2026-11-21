import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fileKind } from "./file-kind";
import { FilePreview } from "./file-preview";

vi.mock("@/modules/pdf-preview", () => ({
  getProjectFileBytes: vi.fn(() => Promise.resolve(new ArrayBuffer(4))),
  ProjectFilePdf: ({ entityId }: { entityId: string }) => <div data-testid="pdf-file">{entityId}</div>,
}));

const entity = (name: string) => ({
  id: "e1",
  name,
  type: "file" as const,
  parentId: null,
  isRoot: false,
  path: name,
});

describe("fileKind", () => {
  it("tells PDFs and images from other files, ignoring case", () => {
    expect(fileKind("figures/flow.PDF")).toBe("pdf");
    expect(fileKind("logo.jpeg")).toBe("image");
    expect(fileKind("data.zip")).toBe("other");
  });
});

describe("FilePreview", () => {
  beforeEach(() => {
    URL.createObjectURL = vi.fn(() => "blob:preview");
    URL.revokeObjectURL = vi.fn();
  });

  it("shows a PDF in the viewer", () => {
    render(<FilePreview projectId="p1" entity={entity("diagram.pdf")} />);
    expect(screen.getByTestId("pdf-file")).toHaveTextContent("e1");
  });

  it("shows an image", async () => {
    render(<FilePreview projectId="p1" entity={entity("logo.png")} />);
    expect(await screen.findByRole("img", { name: "Preview of logo.png" })).toHaveAttribute(
      "src",
      "blob:preview",
    );
  });

  it("explains a file it cannot show", () => {
    render(<FilePreview projectId="p1" entity={entity("data.zip")} />);
    expect(screen.getByText("This is a binary file and can’t be edited here.")).toBeInTheDocument();
  });
});
