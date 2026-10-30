/**
 * Custom Yjs WebSocket provider speaking the spec-29 collab protocol (spec 31).
 *
 * Wire format (matches the pycrdt/y-protocols server): a var-uint message type
 * (`MESSAGE_SYNC` / `MESSAGE_AWARENESS`) followed by a `y-protocols/sync` or
 * `y-protocols/awareness` body. We reuse `y-protocols` + `lib0` so the framing is
 * identical to the server's; only the auth (JWT `?token=`) and reconnect policy
 * are Inkstave-specific.
 */
import * as decoding from "lib0/decoding";
import * as encoding from "lib0/encoding";
import { ObservableV2 } from "lib0/observable";
import {
  applyAwarenessUpdate,
  type Awareness,
  encodeAwarenessUpdate,
  removeAwarenessStates,
} from "y-protocols/awareness";
import * as syncProtocol from "y-protocols/sync";
import type * as Y from "yjs";

import { throttle, type Throttled } from "./throttle";

const MESSAGE_SYNC = 0;
const MESSAGE_AWARENESS = 1;

const RECONNECT_BASE_MS = 500;
const RECONNECT_CAP_MS = 15_000;

const WS_OPEN = 1;

// Spec-29 application close codes that will never recover by retrying — a bad/
// expired token (4401), a non-member/removed collaborator (4403), or a deleted
// project/document (4404). Reconnecting on these would spin forever (spec 35).
const TERMINAL_CLOSE_CODES = new Set([4401, 4403, 4404]);

export type ProviderStatus = "idle" | "connecting" | "connected" | "reconnecting" | "closed";

export interface ProviderOptions {
  /** Full WebSocket URL for the document room (no token); the provider appends `?token=`. */
  url: string;
  documentId: string;
  ydoc: Y.Doc;
  awareness: Awareness;
  getToken: () => string | Promise<string>;
  /** Inject a WebSocket implementation (tests pass a fake). Defaults to the global. */
  WebSocketImpl?: typeof WebSocket;
  /** Connect immediately (default true). */
  connect?: boolean;
  /** Throttle outbound awareness sends (ms, leading+trailing). 0 disables (spec 32). */
  awarenessThrottleMs?: number;
}

interface ProviderEvents {
  status: (event: { status: ProviderStatus }) => void;
  synced: (event: { synced: boolean }) => void;
  "connection-error": (event: { error: unknown }) => void;
}

export class InkstaveWsProvider extends ObservableV2<ProviderEvents> {
  readonly doc: Y.Doc;
  readonly awareness: Awareness;
  readonly documentId: string;

  private readonly _url: string;
  private readonly _getToken: () => string | Promise<string>;
  private readonly _WebSocket: typeof WebSocket;

  private _ws: WebSocket | null = null;
  private _status: ProviderStatus = "idle";
  private _synced = false;
  private _destroyed = false;
  private _stopped = false; // terminal close (4401/4403/4404): no more reconnects
  private _reconnectAttempt = 0;
  private _reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private readonly _awarenessThrottleMs: number;
  private readonly _pendingAwareness = new Set<number>();
  private readonly _flushAwareness: Throttled<[]>;

  constructor(opts: ProviderOptions) {
    super();
    this.doc = opts.ydoc;
    this.awareness = opts.awareness;
    this.documentId = opts.documentId;
    this._url = opts.url;
    this._getToken = opts.getToken;
    this._WebSocket = opts.WebSocketImpl ?? (globalThis.WebSocket as typeof WebSocket);
    this._awarenessThrottleMs = opts.awarenessThrottleMs ?? 0;
    this._flushAwareness = throttle(() => this._flushPendingAwareness(), this._awarenessThrottleMs);

    this.doc.on("update", this._onDocUpdate);
    this.awareness.on("update", this._onAwarenessUpdate);
    if (opts.connect ?? true) void this.connect();
  }

  get status(): ProviderStatus {
    return this._status;
  }

  get synced(): boolean {
    return this._synced;
  }

  private _setStatus(status: ProviderStatus): void {
    if (this._status === status) return;
    this._status = status;
    this.emit("status", [{ status }]);
  }

  async connect(): Promise<void> {
    if (this._destroyed || this._stopped || this._ws) return;
    this._setStatus(this._reconnectAttempt > 0 ? "reconnecting" : "connecting");

    let token: string;
    try {
      token = await this._getToken();
    } catch (error) {
      this.emit("connection-error", [{ error }]);
      this._scheduleReconnect();
      return;
    }
    if (this._destroyed) return;

    const separator = this._url.includes("?") ? "&" : "?";
    const ws = new this._WebSocket(`${this._url}${separator}token=${encodeURIComponent(token)}`);
    ws.binaryType = "arraybuffer";
    this._ws = ws;
    ws.onopen = () => this._onOpen();
    ws.onmessage = (event) => this._onMessage(event.data as ArrayBuffer);
    ws.onclose = (event) => this._onClose(event?.code);
    ws.onerror = (error) => this.emit("connection-error", [{ error }]);
  }

  private _onOpen(): void {
    this._reconnectAttempt = 0;
    this._setStatus("connected");
    // Re-run the Yjs sync handshake on every (re)connect from the current state.
    const encoder = encoding.createEncoder();
    encoding.writeVarUint(encoder, MESSAGE_SYNC);
    syncProtocol.writeSyncStep1(encoder, this.doc);
    this._send(encoding.toUint8Array(encoder));
  }

  private _onMessage(data: ArrayBuffer): void {
    const decoder = decoding.createDecoder(new Uint8Array(data));
    const messageType = decoding.readVarUint(decoder);
    if (messageType === MESSAGE_SYNC) {
      const encoder = encoding.createEncoder();
      encoding.writeVarUint(encoder, MESSAGE_SYNC);
      const syncType = syncProtocol.readSyncMessage(decoder, encoder, this.doc, this);
      if (encoding.length(encoder) > 1) this._send(encoding.toUint8Array(encoder));
      // The server's Step 2 (reply to our Step 1) completes the initial sync.
      if (syncType === syncProtocol.messageYjsSyncStep2 && !this._synced) {
        this._synced = true;
        this.emit("synced", [{ synced: true }]);
      }
    } else if (messageType === MESSAGE_AWARENESS) {
      applyAwarenessUpdate(this.awareness, decoding.readVarUint8Array(decoder), this);
    }
  }

  private _onClose(code?: number): void {
    this._ws = null;
    if (this._destroyed) {
      this._setStatus("closed");
      return;
    }
    if (code !== undefined && TERMINAL_CLOSE_CODES.has(code)) {
      // Auth/permission/not-found close: stop retrying (it cannot recover).
      this._stopped = true;
      this._setStatus("closed");
      this.emit("connection-error", [{ error: new Error(`connection closed (${code})`) }]);
      return;
    }
    // `synced` stays true once achieved: edits remain allowed while reconnecting.
    this._setStatus("reconnecting");
    this._scheduleReconnect();
  }

  private _scheduleReconnect(): void {
    if (this._destroyed || this._stopped || this._reconnectTimer !== null) return;
    const ceiling = Math.min(RECONNECT_CAP_MS, RECONNECT_BASE_MS * 2 ** this._reconnectAttempt);
    const delay = Math.random() * ceiling; // full jitter
    this._reconnectAttempt += 1;
    this._reconnectTimer = setTimeout(() => {
      this._reconnectTimer = null;
      void this.connect();
    }, delay);
  }

  private readonly _onDocUpdate = (update: Uint8Array, origin: unknown): void => {
    if (origin === this) return; // a remote update we just applied — do not echo
    const encoder = encoding.createEncoder();
    encoding.writeVarUint(encoder, MESSAGE_SYNC);
    syncProtocol.writeUpdate(encoder, update);
    this._send(encoding.toUint8Array(encoder));
  };

  private readonly _onAwarenessUpdate = (
    changes: { added: number[]; updated: number[]; removed: number[] },
    origin: unknown,
  ): void => {
    if (origin === this) return;
    const changed = [...changes.added, ...changes.updated, ...changes.removed];
    if (this._awarenessThrottleMs <= 0) {
      this._sendAwareness(changed);
      return;
    }
    // Collapse rapid cursor bursts into bounded sends (the state still updates).
    for (const id of changed) this._pendingAwareness.add(id);
    this._flushAwareness();
  };

  private _flushPendingAwareness(): void {
    const ids = [...this._pendingAwareness];
    this._pendingAwareness.clear();
    this._sendAwareness(ids);
  }

  private _sendAwareness(ids: number[]): void {
    if (ids.length === 0) return;
    const encoder = encoding.createEncoder();
    encoding.writeVarUint(encoder, MESSAGE_AWARENESS);
    encoding.writeVarUint8Array(encoder, encodeAwarenessUpdate(this.awareness, ids));
    this._send(encoding.toUint8Array(encoder));
  }

  private _send(data: Uint8Array): void {
    // While disconnected, edits accumulate in the Y.Doc and are reconciled on the
    // next sync handshake — we never queue raw update frames.
    if (this._ws && this._ws.readyState === WS_OPEN) {
      try {
        this._ws.send(data);
      } catch (error) {
        this.emit("connection-error", [{ error }]);
      }
    }
  }

  /** Resolve once pending local updates have been flushed to the socket (for compile). */
  async flush(): Promise<void> {
    await Promise.resolve(); // let any queued doc-update handlers run
    while (this._ws && this._ws.bufferedAmount > 0) {
      await new Promise((resolve) => setTimeout(resolve, 5));
    }
  }

  destroy(): void {
    if (this._destroyed) return; // safe to call twice (React StrictMode teardown)
    this._destroyed = true;
    this._flushAwareness.cancel();
    if (this._reconnectTimer !== null) {
      clearTimeout(this._reconnectTimer);
      this._reconnectTimer = null;
    }
    this.doc.off("update", this._onDocUpdate);
    this.awareness.off("update", this._onAwarenessUpdate);
    // Broadcast our awareness removal so peers clear our cursor/avatar promptly.
    removeAwarenessStates(this.awareness, [this.doc.clientID], this);
    this._sendAwareness([this.doc.clientID]);
    if (this._ws) {
      const ws = this._ws;
      this._ws = null;
      ws.onopen = null;
      ws.onmessage = null;
      ws.onclose = null;
      ws.onerror = null;
      try {
        ws.close();
      } catch {
        /* already closing */
      }
    }
    this._setStatus("closed");
    super.destroy();
  }
}
