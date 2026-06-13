/** Runtime configuration read from Vite env (build-time inlined). */
function defaultCollabWsUrl(apiBaseUrl: string): string {
  // Derive the spec-29 collab WebSocket base (http->ws). Use the API origin when set;
  // otherwise (apiBaseUrl === "", the same-origin reverse-proxy deploy) derive it from
  // the current page origin at runtime so it works behind a proxy (e.g. Coolify/nginx).
  const origin =
    apiBaseUrl ||
    (typeof window !== "undefined" ? window.location.origin : "http://localhost:8000");
  return `${origin.replace(/^http/, "ws")}/ws/collab`;
}

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export const config = {
  /** Backend origin/base for the API client. */
  apiBaseUrl,
  /** Polling interval (ms) for the compile-status fallback when SSE is unavailable. */
  compilePollIntervalMs: Number(import.meta.env.VITE_COMPILE_POLL_INTERVAL_MS ?? 1000),
  /**
   * Base URL for the spec-29 collab WebSocket (`ws://…/ws/collab`). When empty or unset
   * (the standard same-origin build ships `VITE_COLLAB_WS_URL=""`) it is derived from the
   * current origin — `||`, not `??`, so the empty default still falls through. Set an
   * explicit `ws(s)://…` value only for a split-origin deployment. Live collaboration AND
   * agent diff review both depend on this resolving to a reachable endpoint.
   */
  collabWsUrl: import.meta.env.VITE_COLLAB_WS_URL || defaultCollabWsUrl(apiBaseUrl),
  /** Poll interval (ms) for the notifications-bell unread count. */
  notificationsPollIntervalMs: Number(import.meta.env.VITE_NOTIFICATIONS_POLL_INTERVAL_MS ?? 60000),
  /** Whether the AI agent chat panel is shown (spec 46). Default on; set "false" to hide. */
  agentEnabled: import.meta.env.VITE_AGENT_ENABLED !== "false",
};
