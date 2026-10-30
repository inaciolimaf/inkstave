import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { hasCapability, isReadOnly, usePermissions } from "./usePermissions";

const api = vi.hoisted(() => ({ getPermissions: vi.fn() }));
vi.mock("./api", () => ({ getPermissions: (...a: unknown[]) => api.getPermissions(...a) }));

afterEach(() => vi.clearAllMocks());

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("usePermissions", () => {
  it("fetches the caller's role + capabilities", async () => {
    api.getPermissions.mockResolvedValue({
      role: "editor",
      capabilities: ["doc_write", "compile"],
    });
    const { result } = renderHook(() => usePermissions("p1"), { wrapper });
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(result.current.data!.role).toBe("editor");
    expect(api.getPermissions).toHaveBeenCalledWith("p1");
  });
});

describe("capability helpers", () => {
  it("isReadOnly is true only for viewers", () => {
    expect(isReadOnly({ role: "viewer", capabilities: [] })).toBe(true);
    expect(isReadOnly({ role: "editor", capabilities: [] })).toBe(false);
    expect(isReadOnly(undefined)).toBe(false);
  });

  it("hasCapability checks the capability list", () => {
    const perms = { role: "editor" as const, capabilities: ["doc_write"] };
    expect(hasCapability(perms, "doc_write")).toBe(true);
    expect(hasCapability(perms, "project_delete")).toBe(false);
    expect(hasCapability(undefined, "doc_write")).toBe(false);
  });
});
