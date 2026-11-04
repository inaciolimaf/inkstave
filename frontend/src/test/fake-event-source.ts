/**
 * A hand-driven EventSource for tests: the test opens, fails, and emits named events itself.
 * Install it with `installFakeEventSource()` in a `beforeEach`, and read `FakeEventSource.instances`.
 */
import { vi } from "vitest";

type Listener = (event: MessageEvent<string>) => void;

export class FakeEventSource {
  static instances: FakeEventSource[] = [];

  readonly url: string;
  closed = false;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  private readonly listeners = new Map<string, Set<Listener>>();

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: Listener): void {
    const set = this.listeners.get(type) ?? new Set<Listener>();
    set.add(listener);
    this.listeners.set(type, set);
  }

  close(): void {
    this.closed = true;
  }

  /** The connection is up. */
  open(): void {
    this.onopen?.();
  }

  /** The connection dropped. */
  fail(): void {
    this.onerror?.();
  }

  /** The server sent a named event with this JSON payload. */
  emit(type: string, data: unknown): void {
    this.emitRaw(type, JSON.stringify(data));
  }

  /** The server sent a named event whose data is exactly `raw`. */
  emitRaw(type: string, raw: string): void {
    const event = new MessageEvent<string>(type, { data: raw });
    for (const listener of this.listeners.get(type) ?? []) listener(event);
  }
}

/** Replace the global EventSource with the fake and reset its instances. */
export function installFakeEventSource(): void {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
}

export function latestEventSource(): FakeEventSource {
  const source = FakeEventSource.instances.at(-1);
  if (!source) throw new Error("no EventSource was opened");
  return source;
}
