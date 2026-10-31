/** Whole-screen test harness: the app's real router and providers over a fake API. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RouterProvider } from "react-router-dom";
import { expect, vi } from "vitest";

import { AuthProvider } from "@/modules/auth/auth-context";
import { tokenStore } from "@/lib/token-store";
import { createAppRouter } from "@/router";

type FakeResponse = unknown | ((request: FakeRequest) => unknown);

export interface FakeRequest {
  method: string;
  path: string;
  query: URLSearchParams;
  body: unknown;
}

export const FAKE_USER = {
  id: "user-1",
  email: "ada@example.com",
  display_name: "Ada",
  is_admin: false,
  email_verified: true,
};

/** A failed answer: `fakeApi({ "GET /projects": fakeError(500, "Boom") })`. */
export function fakeError(status: number, message: string) {
  return new Response(JSON.stringify({ error: { message } }), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function toResponse(value: unknown): Response {
  if (value instanceof Response) return value.clone();
  return new Response(JSON.stringify(value), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

/**
 * Swaps `fetch`. Routes are `METHOD /path` without `/api/v1`. An undeclared route answers 404 with
 * the route in the message, so a test fails saying what was missing.
 */
export function fakeApi(routes: Record<string, FakeResponse> = {}) {
  const requests: Array<FakeRequest & { route: string }> = [];

  const fakeFetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input));
    const method = init?.method ?? "GET";
    const path = url.pathname.replace(/^\/api(\/v1)?/, "");
    const body = typeof init?.body === "string" ? JSON.parse(init.body) : init?.body;
    const route = `${method} ${path}`;
    const request = { method, path, query: url.searchParams, body };
    requests.push({ ...request, route });
    if (!(route in routes)) return fakeError(404, `fakeApi: ${route} is not declared`);
    const answer = routes[route];
    return toResponse(typeof answer === "function" ? answer(request) : answer);
  };
  vi.stubGlobal("fetch", vi.fn(fakeFetch));

  return { calls: (route: string) => requests.filter((request) => request.route === route) };
}

/** Render `url` through the app's own router. `signedIn` restores a session as a reload would. */
export async function renderScreen(url: string, { signedIn = false }: { signedIn?: boolean } = {}) {
  if (signedIn) tokenStore.setTokens({ access: "fake-access", refresh: "fake-refresh" });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  const router = createAppRouter([url]);
  const view = render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>
    </QueryClientProvider>,
  );
  // Routes are lazy: returning before the chunk settles makes screen tests fail at random.
  await waitFor(() =>
    expect(router.state.initialized && router.state.navigation.state === "idle").toBe(true),
  );
  return { ...view, router, queryClient, user: userEvent.setup() };
}

/** Spec 106: a screen is one sheet. */
export function expectOneManuscript() {
  expect(document.querySelectorAll("[data-manuscript]")).toHaveLength(1);
}
