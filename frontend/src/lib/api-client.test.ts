import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiClient } from "./api-client";
import { tokenStore } from "./token-store";

interface MockResponse {
  ok: boolean;
  status: number;
  statusText: string;
  json: () => Promise<unknown>;
  text: () => Promise<string>;
}

function mockResponse(status: number, body?: unknown): MockResponse {
  const text = body === undefined ? "" : JSON.stringify(body);
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: "",
    json: async () => JSON.parse(text),
    text: async () => text,
  };
}

const TOKEN_PAIR = {
  access_token: "NEW",
  refresh_token: "RT2",
  token_type: "bearer",
  expires_in: 900,
};

function setFetch(impl: (url: string, init: RequestInit) => Promise<MockResponse>) {
  const fn = vi.fn(impl);
  vi.stubGlobal("fetch", fn);
  return fn;
}

beforeEach(() => {
  tokenStore.clear();
  localStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("apiClient", () => {
  it("injects the Bearer access token", async () => {
    tokenStore.setTokens({ access: "AT", refresh: "RT" });
    const fetchMock = setFetch(async () => mockResponse(200, { id: "1" }));
    await apiClient.get("/api/v1/users/me");
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer AT");
  });

  it("does not attach auth when auth:false", async () => {
    tokenStore.setTokens({ access: "AT", refresh: "RT" });
    const fetchMock = setFetch(async () => mockResponse(200, TOKEN_PAIR));
    await apiClient.post("/api/v1/auth/login", { email: "a@b.c" }, { auth: false });
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect((init.headers as Record<string, string>).Authorization).toBeUndefined();
  });

  it("refreshes once on 401 and replays the original request", async () => {
    tokenStore.setTokens({ access: "OLD", refresh: "RT" });
    const fetchMock = setFetch(async (url, init) => {
      if (url.endsWith("/auth/refresh")) return mockResponse(200, TOKEN_PAIR);
      const auth = (init.headers as Record<string, string>).Authorization;
      return auth === "Bearer OLD"
        ? mockResponse(401, { error: { message: "expired" } })
        : mockResponse(200, { id: "1" });
    });
    const result = await apiClient.get<{ id: string }>("/api/v1/users/me");
    expect(result).toEqual({ id: "1" });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(tokenStore.getAccessToken()).toBe("NEW");
  });

  it("dedupes concurrent 401s into a single refresh", async () => {
    tokenStore.setTokens({ access: "OLD", refresh: "RT" });
    let refreshCalls = 0;
    setFetch(async (url, init) => {
      if (url.endsWith("/auth/refresh")) {
        refreshCalls += 1;
        return mockResponse(200, TOKEN_PAIR);
      }
      const auth = (init.headers as Record<string, string>).Authorization;
      return auth === "Bearer OLD"
        ? mockResponse(401, { error: { message: "x" } })
        : mockResponse(200, { ok: true });
    });
    const [a, b] = await Promise.all([apiClient.get("/api/v1/a"), apiClient.get("/api/v1/b")]);
    expect(refreshCalls).toBe(1);
    expect(a).toEqual({ ok: true });
    expect(b).toEqual({ ok: true });
  });

  it("clears tokens and throws when refresh fails", async () => {
    tokenStore.setTokens({ access: "OLD", refresh: "RT" });
    setFetch(async (url) => {
      if (url.endsWith("/auth/refresh"))
        return mockResponse(401, { error: { message: "bad refresh" } });
      return mockResponse(401, { error: { message: "expired" } });
    });
    await expect(apiClient.get("/api/v1/users/me")).rejects.toBeInstanceOf(ApiError);
    expect(tokenStore.getAccessToken()).toBeNull();
    expect(tokenStore.getRefreshToken()).toBeNull();
  });

  it("parses 422 field errors into ApiError.fieldErrors", async () => {
    setFetch(async () =>
      mockResponse(422, {
        error: {
          type: "validation_error",
          message: "Request validation failed",
          details: [
            { loc: ["body", "email"], msg: "value is not a valid email", type: "value_error" },
          ],
        },
      }),
    );
    await expect(
      apiClient.post("/api/v1/auth/register", {}, { auth: false }),
    ).rejects.toMatchObject({
      status: 422,
      fieldErrors: { email: "value is not a valid email" },
    });
  });

  it("parses a generic error message into ApiError.detail", async () => {
    setFetch(async () =>
      mockResponse(409, { error: { type: "conflict", message: "Already exists." } }),
    );
    await expect(
      apiClient.post("/api/v1/auth/register", {}, { auth: false }),
    ).rejects.toMatchObject({
      status: 409,
      detail: "Already exists.",
    });
  });
});
