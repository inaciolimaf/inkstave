import { beforeEach, describe, expect, it } from "vitest";

import { tokenStore } from "./token-store";

const REFRESH_KEY = "inkstave.refresh_token";

beforeEach(() => {
  tokenStore.clear();
  localStorage.clear();
});

describe("tokenStore", () => {
  it("keeps the access token in memory and the refresh token in localStorage", () => {
    tokenStore.setTokens({ access: "ACCESS", refresh: "REFRESH" });
    expect(tokenStore.getAccessToken()).toBe("ACCESS");
    expect(tokenStore.getRefreshToken()).toBe("REFRESH");
    expect(localStorage.getItem(REFRESH_KEY)).toBe("REFRESH");
  });

  it("never writes the access token to localStorage", () => {
    tokenStore.setTokens({ access: "ACCESS", refresh: "REFRESH" });
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i)!;
      expect(localStorage.getItem(key)).not.toBe("ACCESS");
    }
  });

  it("clears both tokens", () => {
    tokenStore.setTokens({ access: "ACCESS", refresh: "REFRESH" });
    tokenStore.clear();
    expect(tokenStore.getAccessToken()).toBeNull();
    expect(tokenStore.getRefreshToken()).toBeNull();
    expect(localStorage.getItem(REFRESH_KEY)).toBeNull();
  });

  it("notifies subscribers on change and stops after unsubscribe", () => {
    let calls = 0;
    const unsubscribe = tokenStore.subscribe(() => {
      calls += 1;
    });
    tokenStore.setTokens({ access: "A", refresh: "R" });
    tokenStore.clear();
    expect(calls).toBe(2);
    unsubscribe();
    tokenStore.setTokens({ access: "A2", refresh: "R2" });
    expect(calls).toBe(2);
  });
});
