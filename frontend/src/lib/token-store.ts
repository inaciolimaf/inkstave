/**
 * Token storage.
 *
 * The **access token lives in memory only** (never in localStorage — that would
 * be exfiltratable by XSS). The **refresh token is persisted in localStorage**
 * so a full page reload can re-bootstrap a session (see the ADR for the
 * trade-off; an httpOnly-cookie refresh token is a future hardening option).
 */

const REFRESH_KEY = "inkstave.refresh_token";

let accessToken: string | null = null;
const listeners = new Set<() => void>();

function notify(): void {
  for (const listener of listeners) listener();
}

export const tokenStore = {
  getAccessToken(): string | null {
    return accessToken;
  },

  getRefreshToken(): string | null {
    try {
      return localStorage.getItem(REFRESH_KEY);
    } catch {
      return null;
    }
  },

  setTokens(tokens: { access: string; refresh: string }): void {
    accessToken = tokens.access;
    try {
      localStorage.setItem(REFRESH_KEY, tokens.refresh);
    } catch {
      // Ignore storage failures (e.g. private mode); access token still works.
    }
    notify();
  },

  clear(): void {
    accessToken = null;
    try {
      localStorage.removeItem(REFRESH_KEY);
    } catch {
      // ignore
    }
    notify();
  },

  /** Subscribe to token changes; returns an unsubscribe function. */
  subscribe(listener: () => void): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
};
