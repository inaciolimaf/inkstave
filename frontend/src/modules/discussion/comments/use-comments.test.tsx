import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { installFakeEventSource, latestEventSource } from "@/test/fake-event-source";

import type { CommentThread } from "./api";
import { useCommentThreads } from "./use-comments";

const api = vi.hoisted(() => ({ fetchThreads: vi.fn() }));
vi.mock("./api", async (importOriginal) => ({ ...(await importOriginal<object>()), ...api }));

const thread = { id: "t1", messages: [] } as unknown as CommentThread;

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  installFakeEventSource();
});

afterEach(() => {
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe("useCommentThreads", () => {
  it("refetches when a comment event arrives over the project stream", async () => {
    api.fetchThreads.mockResolvedValueOnce([]).mockResolvedValueOnce([thread]);
    const { result } = renderHook(() => useCommentThreads("p1"), { wrapper });
    await waitFor(() => expect(result.current.data).toEqual([]));

    act(() => latestEventSource().emit("comment.thread_created", { id: 1, type: "comment.thread_created" }));

    await waitFor(() => expect(result.current.data).toEqual([thread]));
    expect(api.fetchThreads).toHaveBeenCalledTimes(2);
  });

  it("ignores chat events", async () => {
    api.fetchThreads.mockResolvedValue([]);
    const { result } = renderHook(() => useCommentThreads("p1"), { wrapper });
    await waitFor(() => expect(result.current.data).toEqual([]));

    act(() => latestEventSource().emit("chat.message_created", { id: 2, type: "chat.message_created" }));

    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(api.fetchThreads).toHaveBeenCalledTimes(1);
  });
});
