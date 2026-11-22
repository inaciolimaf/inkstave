import { afterEach, describe, expect, it, vi } from "vitest";

import {
  AWARENESS_FRAME,
  ControllableWS,
  makeAwarenessProvider,
  makeBareProvider,
  tick,
} from "./InkstaveWsProvider.test-helpers";

// --- state machine / backoff / teardown with a controllable fake socket ---- #

describe("InkstaveWsProvider lifecycle", () => {
  afterEach(() => {
    ControllableWS.instances = [];
    vi.useRealTimers();
  });

  it("transitions connecting -> connected and sends sync step 1", async () => {
    const { provider } = makeBareProvider();
    expect(provider.status).toBe("connecting");
    await tick(); // getToken + socket creation
    ControllableWS.instances[0].open();
    expect(provider.status).toBe("connected");
    expect(ControllableWS.instances[0].sent.length).toBe(1); // sync step 1
    provider.destroy();
  });

  it("goes reconnecting on drop and retries with backoff (AC3)", async () => {
    vi.useFakeTimers();
    const { provider } = makeBareProvider();
    await vi.advanceTimersByTimeAsync(0);
    ControllableWS.instances[0].open();
    ControllableWS.instances[0].fail(); // socket dropped
    expect(provider.status).toBe("reconnecting");
    await vi.advanceTimersByTimeAsync(15_000); // past the backoff cap
    expect(ControllableWS.instances.length).toBe(2); // a new connection attempt
    provider.destroy();
  });

  it("stops reconnecting after a terminal auth close (4401) — no spin (spec 35)", async () => {
    vi.useFakeTimers();
    const { provider } = makeBareProvider();
    await vi.advanceTimersByTimeAsync(0);
    ControllableWS.instances[0].open();
    ControllableWS.instances[0].fail(4401); // bad/expired token — cannot recover
    expect(provider.status).toBe("closed");
    await vi.advanceTimersByTimeAsync(60_000); // would have spun many times
    expect(ControllableWS.instances.length).toBe(1); // no further attempts
    provider.destroy();
  });

  it.each([4403, 4404])("stops reconnecting after a terminal %i close", async (code) => {
    vi.useFakeTimers();
    const { provider } = makeBareProvider();
    await vi.advanceTimersByTimeAsync(0);
    ControllableWS.instances[0].open();
    ControllableWS.instances[0].fail(code);
    await vi.advanceTimersByTimeAsync(60_000);
    expect(ControllableWS.instances.length).toBe(1);
    provider.destroy();
  });

  it("does not reconnect after destroy (AC7)", async () => {
    vi.useFakeTimers();
    const { provider } = makeBareProvider();
    await vi.advanceTimersByTimeAsync(0);
    ControllableWS.instances[0].open();
    provider.destroy();
    expect(provider.status).toBe("closed");
    ControllableWS.instances[0].fail(); // onclose is detached -> no effect
    await vi.advanceTimersByTimeAsync(20_000);
    expect(ControllableWS.instances.length).toBe(1); // no further attempts
  });
});

// --- terminal close codes: the server closes after accept, so the browser sees them #

describe("InkstaveWsProvider auth close handling (4401 / 4403 / 4404)", () => {
  afterEach(() => {
    ControllableWS.instances = [];
    vi.useRealTimers();
  });

  /** A provider whose token is replaced by `refreshToken`, which reports success or failure. */
  function makeRefreshingProvider(refreshOk: boolean) {
    let token = "old-token";
    const refreshToken = vi.fn(async () => {
      if (refreshOk) token = "new-token";
      return refreshOk;
    });
    const made = makeBareProvider({ getToken: () => token, refreshToken });
    return { ...made, refreshToken };
  }

  it("refreshes the token once after 4401 and reconnects with the new one", async () => {
    vi.useFakeTimers();
    const { provider, refreshToken } = makeRefreshingProvider(true);
    await vi.advanceTimersByTimeAsync(0);
    ControllableWS.instances[0].open();
    ControllableWS.instances[0].fail(4401);
    await vi.advanceTimersByTimeAsync(0);

    expect(refreshToken).toHaveBeenCalledTimes(1);
    expect(ControllableWS.instances.length).toBe(2);
    expect(ControllableWS.instances[1].url).toContain("token=new-token");
    provider.destroy();
  });

  it("stops when the refresh after 4401 fails", async () => {
    vi.useFakeTimers();
    const { provider, refreshToken } = makeRefreshingProvider(false);
    await vi.advanceTimersByTimeAsync(0);
    ControllableWS.instances[0].open();
    ControllableWS.instances[0].fail(4401);
    await vi.advanceTimersByTimeAsync(60_000);

    expect(refreshToken).toHaveBeenCalledTimes(1);
    expect(ControllableWS.instances.length).toBe(1);
    expect(provider.status).toBe("closed");
    provider.destroy();
  });

  it("does not refresh a second time when 4401 comes again before the session syncs", async () => {
    vi.useFakeTimers();
    const { provider, refreshToken } = makeRefreshingProvider(true);
    await vi.advanceTimersByTimeAsync(0);
    ControllableWS.instances[0].open();
    ControllableWS.instances[0].fail(4401);
    await vi.advanceTimersByTimeAsync(0);
    ControllableWS.instances[1].open();
    ControllableWS.instances[1].fail(4401); // refreshed token refused as well
    await vi.advanceTimersByTimeAsync(60_000);

    expect(refreshToken).toHaveBeenCalledTimes(1);
    expect(ControllableWS.instances.length).toBe(2);
    expect(provider.status).toBe("closed");
    provider.destroy();
  });

  it.each([4403, 4404])("stops on %i without asking for a token refresh", async (code) => {
    vi.useFakeTimers();
    const { provider, refreshToken } = makeRefreshingProvider(true);
    await vi.advanceTimersByTimeAsync(0);
    ControllableWS.instances[0].open();
    ControllableWS.instances[0].fail(code);
    await vi.advanceTimersByTimeAsync(60_000);

    expect(refreshToken).not.toHaveBeenCalled();
    expect(ControllableWS.instances.length).toBe(1);
    provider.destroy();
  });

  it("answers a heartbeat ping with a pong (keepalive, COLLAB_WS_PING_INTERVAL_SECONDS)", async () => {
    vi.useFakeTimers();
    const { provider } = makeBareProvider();
    await vi.advanceTimersByTimeAsync(0);
    const ws = ControllableWS.instances[0];
    ws.open();
    ws.sent.length = 0;
    ws.onmessage?.({ data: new Uint8Array([2]).buffer }); // server ping: tag 2

    expect(ws.sent.map((frame) => Array.from(frame))).toEqual([[3]]); // pong: tag 3
    provider.destroy();
  });
});

// --- awareness throttle integration over the wire (spec 32 §8) -------------- #

describe("InkstaveWsProvider awareness throttle (spec 32 §8 / AC5)", () => {
  afterEach(() => {
    ControllableWS.instances = [];
    vi.useRealTimers();
  });

  it("collapses rapid awareness changes into a bounded number of wire frames", async () => {
    vi.useFakeTimers();
    const { awareness, provider } = makeAwarenessProvider(50);
    await vi.advanceTimersByTimeAsync(0); // getToken + socket creation
    const ws = ControllableWS.instances[0];
    ws.open();
    ws.sent.length = 0; // drop the initial sync-step-1 frame from the count

    // Many rapid selection/cursor changes inside a single throttle window.
    for (let i = 0; i < 25; i++) {
      awareness.setLocalStateField("cursor", { anchor: i, head: i });
    }
    // Flush the trailing edge of the throttle window.
    await vi.advanceTimersByTimeAsync(50);

    const awarenessFrames = ws.sent.filter((frame) => frame[0] === AWARENESS_FRAME);
    // Leading + trailing only — a small constant, NOT one frame per change.
    expect(awarenessFrames.length).toBeGreaterThan(0);
    expect(awarenessFrames.length).toBeLessThanOrEqual(2);
    expect(awarenessFrames.length).toBeLessThan(25);

    provider.destroy();
  });
});
