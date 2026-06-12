/**
 * Typed fetch wrapper with Bearer injection and transparent refresh-on-401.
 *
 * - Adds `Authorization: Bearer <accessToken>` when one is available.
 * - On a `401` (for a non-refresh, authed request), awaits a **single shared**
 *   refresh promise, then **replays the original request once**.
 * - Concurrent 401s share one in-flight refresh (no thundering herd).
 * - On refresh failure, clears tokens (the auth context observes this and
 *   redirects to /login) and surfaces a typed {@link ApiError}.
 */
import { config } from "@/config";
import { tokenStore } from "@/lib/token-store";
import type { FieldErrors, TokenPair } from "@/types";

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;
  readonly fieldErrors?: FieldErrors;
  /** Raw `error.details` array from the envelope (e.g. version-conflict state). */
  readonly details?: unknown[];

  constructor(status: number, detail: string, fieldErrors?: FieldErrors, details?: unknown[]) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.fieldErrors = fieldErrors;
    this.details = details;
  }
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  /** Attach the Bearer token and enable refresh-on-401 (default true). */
  auth?: boolean;
}

let refreshPromise: Promise<boolean> | null = null;

function url(path: string): string {
  return `${config.apiBaseUrl}${path}`;
}

/** Run the actual refresh call once; shared by all concurrent callers. */
async function performRefresh(): Promise<boolean> {
  const refresh = tokenStore.getRefreshToken();
  if (!refresh) return false;
  let res: Response;
  try {
    res = await fetch(url("/api/v1/auth/refresh"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refresh }),
    });
  } catch {
    return false;
  }
  if (!res.ok) {
    tokenStore.clear();
    return false;
  }
  const pair = (await res.json()) as TokenPair;
  tokenStore.setTokens({ access: pair.access_token, refresh: pair.refresh_token });
  return true;
}

/** De-duplicate concurrent refreshes into a single in-flight promise. */
export function refreshTokens(): Promise<boolean> {
  if (!refreshPromise) {
    refreshPromise = performRefresh().finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

async function toApiError(res: Response): Promise<ApiError> {
  let detail = res.statusText || "Request failed";
  let fieldErrors: FieldErrors | undefined;
  let rawDetails: unknown[] | undefined;
  try {
    const data = await res.json();
    const error = data?.error;
    if (error) {
      detail = error.message ?? detail;
      if (Array.isArray(error.details)) {
        rawDetails = error.details;
        const collected: FieldErrors = {};
        for (const item of error.details) {
          const loc: unknown[] = Array.isArray(item.loc) ? item.loc : [];
          // Skip the leading "body"/"query" segment to get the field name.
          const field = loc.slice(1).join(".") || String(loc[loc.length - 1] ?? "");
          if (field) collected[field] = String(item.msg ?? "");
        }
        if (Object.keys(collected).length > 0) fieldErrors = collected;
      }
    } else if (typeof data?.detail === "string") {
      detail = data.detail;
    }
  } catch {
    // Non-JSON body — keep the status text.
  }
  return new ApiError(res.status, detail, fieldErrors, rawDetails);
}

async function parseBody<T>(res: Response): Promise<T> {
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

async function request<T>(path: string, options: RequestOptions, isRetry = false): Promise<T> {
  const auth = options.auth ?? true;
  const headers: Record<string, string> = {};
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  const access = tokenStore.getAccessToken();
  if (auth && access) headers["Authorization"] = `Bearer ${access}`;

  const res = await fetch(url(path), {
    method: options.method ?? "GET",
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });

  const isRefreshCall = path.endsWith("/auth/refresh");
  if (res.status === 401 && auth && !isRetry && !isRefreshCall) {
    const refreshed = await refreshTokens();
    if (refreshed) return request<T>(path, options, true);
    throw await toApiError(res);
  }

  if (!res.ok) throw await toApiError(res);
  return parseBody<T>(res);
}

type BodylessOptions = Omit<RequestOptions, "method" | "body">;

export const apiClient = {
  get: <T>(path: string, options: BodylessOptions = {}) =>
    request<T>(path, { ...options, method: "GET" }),
  post: <T>(path: string, body?: unknown, options: BodylessOptions = {}) =>
    request<T>(path, { ...options, method: "POST", body }),
  put: <T>(path: string, body?: unknown, options: BodylessOptions = {}) =>
    request<T>(path, { ...options, method: "PUT", body }),
  patch: <T>(path: string, body?: unknown, options: BodylessOptions = {}) =>
    request<T>(path, { ...options, method: "PATCH", body }),
  delete: <T>(path: string, options: BodylessOptions = {}) =>
    request<T>(path, { ...options, method: "DELETE" }),
};
