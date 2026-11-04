import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as Y from "yjs";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { installFakeEventSource } from "@/test/fake-event-source";
import { renderWithProviders } from "@/test/utils";

import { encodeAnchor } from "./anchors";
import type { CommentThread } from "./api";
import { CommentsPanel, type CommentsPanelProps } from "./comments-panel";

const api = vi.hoisted(() => ({
  createThread: vi.fn(),
  replyToThread: vi.fn(),
  editMessage: vi.fn(),
  deleteMessage: vi.fn(),
  setThreadResolved: vi.fn(),
  fetchThreads: vi.fn(),
}));
vi.mock("./api", async (importOriginal) => ({ ...(await importOriginal<object>()), ...api }));
vi.mock("@/modules/auth/auth-context", () => ({
  useAuth: () => ({ user: { id: "me", display_name: "Me" } }),
}));

const BODY = "Intro.\n\nWe read the results and they were clear.\n";

/** A thread whose anchors cover `text` as it is in `ytext`, or collapsed when `text` is null. */
function thread(
  id: string,
  ytext: Y.Text,
  text: string | null,
  options: { documentId?: string; resolved?: boolean; createdAt?: string } = {},
): CommentThread {
  const at = text ? ytext.toString().indexOf(text) : 0;
  const anchors = text ? encodeAnchor(ytext, at, at + text.length) : encodeAnchor(ytext, 0, 0);
  return {
    id,
    document_id: options.documentId ?? "doc-main",
    anchor_start: anchors.anchorStart,
    anchor_end: anchors.anchorEnd,
    quoted_text: text ?? "vanished quote",
    author: { id: "ana", display_name: "Ana" },
    created_at: options.createdAt ?? "2026-11-04T10:00:00Z",
    resolved_at: options.resolved ? "2026-11-04T11:00:00Z" : null,
    resolved_by: null,
    messages: [
      {
        id: `${id}-m1`,
        body: `Comment ${id}`,
        author: { id: "ana", display_name: "Ana" },
        mentions: [],
        created_at: "2026-11-04T10:00:00Z",
        edited_at: null,
        deleted: false,
      },
    ],
  } as unknown as CommentThread;
}

function renderPanel(overrides: Partial<CommentsPanelProps> & { threads: CommentThread[]; ytext: Y.Text }) {
  const props: CommentsPanelProps = {
    open: true,
    onOpenChange: vi.fn(),
    wide: true,
    projectId: "p1",
    currentDocumentId: "doc-main",
    fileName: (id) => (id === "doc-main" ? "main.tex" : "refs.tex"),
    members: [{ id: "ben", name: "Ben" }],
    meId: "me",
    selectedId: null,
    onSelect: vi.fn(),
    draft: null,
    creating: false,
    onCreate: vi.fn(),
    onDraftCancel: vi.fn(),
    ...overrides,
  };
  return renderWithProviders(<CommentsPanel {...props} />);
}

beforeEach(() => {
  installFakeEventSource();
  api.fetchThreads.mockResolvedValue([]);
});

afterEach(() => {
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe("CommentsPanel", () => {
  it("lists the open threads of this file in text order, by default", () => {
    const ytext = new Y.Doc().getText("content");
    ytext.insert(0, BODY);
    const second = thread("second", ytext, "clear");
    const first = thread("first", ytext, "results");
    const elsewhere = thread("elsewhere", ytext, "Intro", { documentId: "doc-refs" });
    renderPanel({ threads: [second, first, elsewhere], ytext });

    const quotes = screen.getAllByRole("button", { name: /results|clear/ }).map((b) => b.textContent);
    expect(quotes[0]).toContain("results");
    expect(quotes[1]).toContain("clear");
    expect(screen.queryByText("Comment elsewhere")).not.toBeInTheDocument();
  });

  it("shows the threads of every file on the all-files scope, with the file name", async () => {
    const user = userEvent.setup();
    const ytext = new Y.Doc().getText("content");
    ytext.insert(0, BODY);
    renderPanel({
      threads: [
        thread("here", ytext, "results"),
        thread("there", ytext, "Intro", { documentId: "doc-refs" }),
      ],
      ytext,
    });

    await user.click(screen.getByRole("button", { name: "All files" }));
    expect(screen.getByText("Comment there")).toBeInTheDocument();
    expect(screen.getByText("refs.tex")).toBeInTheDocument();
  });

  it("filters by status, and resolved threads appear under Resolved", async () => {
    const user = userEvent.setup();
    const ytext = new Y.Doc().getText("content");
    ytext.insert(0, BODY);
    renderPanel({
      threads: [thread("open-one", ytext, "results"), thread("done-one", ytext, "clear", { resolved: true })],
      ytext,
    });

    expect(screen.getByText("Comment open-one")).toBeInTheDocument();
    expect(screen.queryByText("Comment done-one")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Resolved" }));
    expect(screen.getByText("Comment done-one")).toBeInTheDocument();
    expect(screen.queryByText("Comment open-one")).not.toBeInTheDocument();
  });

  it("marks a thread whose text was removed as detached, and keeps its quote", () => {
    const ytext = new Y.Doc().getText("content");
    ytext.insert(0, BODY);
    const gone = thread("gone-one", ytext, null);
    renderPanel({ threads: [gone], ytext });

    expect(screen.getByText("Detached comment")).toBeInTheDocument();
    expect(screen.getByText(/The text this comment was on was removed/)).toBeInTheDocument();
    expect(screen.getByText(/vanished quote/)).toBeInTheDocument();
  });

  it("shows the composer for a draft and sends its body with the picked mentions", async () => {
    const user = userEvent.setup();
    const ytext = new Y.Doc().getText("content");
    ytext.insert(0, BODY);
    const onCreate = vi.fn();
    renderPanel({ threads: [], ytext, draft: { quote: "the results" }, onCreate });

    const box = screen.getByRole("combobox", { name: "New comment" });
    await user.type(box, "@Be");
    await user.click(await screen.findByRole("option", { name: "Ben" }));
    await user.type(box, "please check");
    await user.click(screen.getByRole("button", { name: "Comment" }));

    expect(onCreate).toHaveBeenCalledWith("@Ben please check", ["ben"]);
  });

  it("is a sheet on a narrow screen and not a column", async () => {
    const ytext = new Y.Doc().getText("content");
    ytext.insert(0, BODY);
    renderPanel({ threads: [thread("one", ytext, "results")], ytext, wide: false });
    await waitFor(() => expect(screen.getByRole("dialog", { name: "Comments" })).toBeInTheDocument());
    expect(within(screen.getByRole("dialog")).getByText("Comment one")).toBeInTheDocument();
  });
});
