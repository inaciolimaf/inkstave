import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LogPanel } from "./LogPanel";
import type { CompileStatus } from "./types";

function meta(over: Partial<CompileStatus> = {}): CompileStatus {
  return {
    id: "c1",
    project_id: "p1",
    status: "failure",
    main_file: "main.tex",
    has_pdf: false,
    created_at: "2026-06-09T00:00:00Z",
    started_at: null,
    finished_at: null,
    duration_ms: 2500,
    exit_code: 1,
    error_message: null,
    log_excerpt: null,
    artifact_manifest: null,
    ...over,
  };
}

afterEach(() => vi.restoreAllMocks());

describe("LogPanel", () => {
  it("renders nothing when collapsed", () => {
    const { container } = render(
      <LogPanel
        expanded={false}
        log={null}
        loading={false}
        error={null}
        onFetch={vi.fn()}
        meta={null}
      />,
    );
    expect(screen.queryByRole("region", { name: "Compile log" })).toBeNull();
    expect(container).toBeEmptyDOMElement();
  });

  it("lazy-fetches the log when expanded and shows the status line", () => {
    const onFetch = vi.fn();
    render(
      <LogPanel
        expanded
        log={"! Undefined control sequence."}
        loading={false}
        error={null}
        onFetch={onFetch}
        meta={meta()}
      />,
    );
    expect(onFetch).toHaveBeenCalled();
    expect(screen.getByRole("region", { name: "Compile log" })).toHaveTextContent(
      "! Undefined control sequence.",
    );
    expect(screen.getByText("failure · 2.5s · exit 1")).toBeInTheDocument();
  });

  it("copies the log to the clipboard", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    render(
      <LogPanel
        expanded
        log="log body"
        loading={false}
        error={null}
        onFetch={vi.fn()}
        meta={null}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Copy log to clipboard" }));
    expect(writeText).toHaveBeenCalledWith("log body");
    expect(await screen.findByText("Copied")).toBeInTheDocument();
  });
});
