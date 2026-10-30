import { afterEach, describe, expect, it, vi } from "vitest";

import { ImportUploadError, importProjectZip } from "./api";

/** Minimal controllable XMLHttpRequest stand-in for the multipart upload. */
class FakeXHR {
  static last: FakeXHR | null = null;
  upload: { onprogress: ((e: ProgressEvent) => void) | null } = { onprogress: null };
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  status = 0;
  responseText = "";
  method = "";
  url = "";
  headers: Record<string, string> = {};
  body: FormData | null = null;

  open(method: string, url: string) {
    this.method = method;
    this.url = url;
  }
  setRequestHeader(key: string, value: string) {
    this.headers[key] = value;
  }
  send(body: FormData) {
    this.body = body;
    FakeXHR.last = this;
  }
}

afterEach(() => vi.restoreAllMocks());

describe("importProjectZip", () => {
  it("builds multipart FormData with the file and trimmed name", () => {
    vi.stubGlobal("XMLHttpRequest", FakeXHR);
    const file = new File([new Uint8Array([1, 2, 3])], "paper.zip", { type: "application/zip" });
    void importProjectZip(file, "  My Paper  ");

    const xhr = FakeXHR.last!;
    expect(xhr.method).toBe("POST");
    expect(xhr.url).toContain("/api/v1/projects/import");
    expect((xhr.body!.get("file") as File).name).toBe("paper.zip");
    expect(xhr.body!.get("name")).toBe("My Paper");
  });

  it("omits the name field when blank", () => {
    vi.stubGlobal("XMLHttpRequest", FakeXHR);
    const file = new File(["x"], "p.zip", { type: "application/zip" });
    void importProjectZip(file, "   ");
    expect(FakeXHR.last!.body!.get("name")).toBeNull();
  });

  it("reports progress then resolves with the camelCased import row", async () => {
    vi.stubGlobal("XMLHttpRequest", FakeXHR);
    const fractions: number[] = [];
    const file = new File(["x"], "p.zip", { type: "application/zip" });
    const promise = importProjectZip(file, undefined, (f) => fractions.push(f));

    const xhr = FakeXHR.last!;
    xhr.upload.onprogress!({ lengthComputable: true, loaded: 5, total: 10 } as ProgressEvent);
    xhr.status = 202;
    xhr.responseText = JSON.stringify({
      import_id: "imp-1",
      project_id: "proj-1",
      status: "queued",
      entries_total: null,
      entries_imported: null,
      error_type: null,
      error_message: null,
    });
    xhr.onload!();

    const row = await promise;
    expect(fractions).toContain(0.5);
    expect(fractions.at(-1)).toBe(1);
    expect(row).toMatchObject({ importId: "imp-1", projectId: "proj-1", status: "queued" });
  });

  it("rejects with ImportUploadError carrying error_type on a 4xx", async () => {
    vi.stubGlobal("XMLHttpRequest", FakeXHR);
    const file = new File(["x"], "p.zip", { type: "application/zip" });
    const promise = importProjectZip(file);

    const xhr = FakeXHR.last!;
    xhr.status = 413;
    xhr.responseText = JSON.stringify({
      error: { type: "file_too_large", message: "too big" },
    });
    xhr.onload!();

    await expect(promise).rejects.toBeInstanceOf(ImportUploadError);
    await promise.catch((err: ImportUploadError) => {
      expect(err.status).toBe(413);
      expect(err.errorType).toBe("file_too_large");
    });
  });
});
