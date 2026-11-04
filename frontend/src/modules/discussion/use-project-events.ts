/**
 * The project event stream on the client (spec 117): one EventSource per open project, shared
 * by every subscriber, reconnecting with backoff. Chat uses it now, comments (spec 118) reuse it.
 *
 * The server does not replay on reconnect. A subscriber gets `onOpen` after every (re)connect and
 * refetches what it shows, so it never relies on events it missed while the stream was down.
 */
import { useEffect, useRef } from "react";

import { config } from "@/config";
import { tokenStore } from "@/lib/token-store";

/** Every event type the server sends. A spec that adds one (118's `comment.*`) adds it here. */
export const PROJECT_EVENT_TYPES = [
  "chat.message_created",
  "chat.message_deleted",
  "comment.thread_created",
  "comment.message_created",
  "comment.message_updated",
  "comment.message_deleted",
  "comment.thread_resolved",
  "comment.thread_reopened",
] as const;

export interface ProjectEvent {
  id: number;
  type: string;
  payload: unknown;
}

export interface ProjectEventHandlers {
  onEvent?: (event: ProjectEvent) => void;
  /** Runs on every connection, the first one included. */
  onOpen?: () => void;
}

// The collab provider's policy (InkstaveWsProvider): full jitter over an exponential ceiling.
const RECONNECT_BASE_MS = 500;
const RECONNECT_CAP_MS = 15_000;

interface SharedStream {
  source: EventSource | null;
  handlers: Set<ProjectEventHandlers>;
  attempts: number;
  timer: ReturnType<typeof setTimeout> | null;
}

const streams = new Map<string, SharedStream>();

/** The SSE URL with the access token in the query: EventSource cannot send headers. */
export function projectEventsUrl(projectId: string): string {
  const token = tokenStore.getAccessToken();
  const query = token ? `?access_token=${encodeURIComponent(token)}` : "";
  return `${config.apiBaseUrl}/api/v1/projects/${projectId}/events${query}`;
}

function deliver(stream: SharedStream, message: MessageEvent<string>): void {
  let event: ProjectEvent;
  try {
    event = JSON.parse(message.data) as ProjectEvent;
  } catch {
    return; // a frame that is not JSON is not ours to act on
  }
  for (const handlers of [...stream.handlers]) handlers.onEvent?.(event);
}

function notifyOpen(stream: SharedStream): void {
  for (const handlers of [...stream.handlers]) handlers.onOpen?.();
}

function scheduleReconnect(projectId: string, stream: SharedStream): void {
  if (stream.handlers.size === 0) return;
  const ceiling = Math.min(RECONNECT_CAP_MS, RECONNECT_BASE_MS * 2 ** stream.attempts);
  stream.attempts += 1;
  stream.timer = setTimeout(() => {
    stream.timer = null;
    connect(projectId, stream);
  }, Math.random() * ceiling);
}

function connect(projectId: string, stream: SharedStream): void {
  // The token is read at each connect, so a reconnect after a refresh carries the new one.
  const source = new EventSource(projectEventsUrl(projectId));
  stream.source = source;
  source.onopen = () => {
    stream.attempts = 0;
    notifyOpen(stream);
  };
  for (const type of PROJECT_EVENT_TYPES) {
    source.addEventListener(type, (message) => deliver(stream, message as MessageEvent<string>));
  }
  source.onerror = () => {
    source.close();
    stream.source = null;
    scheduleReconnect(projectId, stream);
  };
}

function closeStream(stream: SharedStream): void {
  if (stream.timer !== null) clearTimeout(stream.timer);
  stream.timer = null;
  stream.source?.close();
  stream.source = null;
}

/** Subscribe to a project's events. The first subscriber opens the stream; the last one closes it. */
export function subscribeProjectEvents(projectId: string, handlers: ProjectEventHandlers): () => void {
  let stream = streams.get(projectId);
  if (!stream) {
    stream = { source: null, handlers: new Set(), attempts: 0, timer: null };
    streams.set(projectId, stream);
    connect(projectId, stream);
  }
  const current = stream;
  current.handlers.add(handlers);
  return () => {
    current.handlers.delete(handlers);
    if (current.handlers.size > 0) return;
    closeStream(current);
    if (streams.get(projectId) === current) streams.delete(projectId);
  };
}

/** Subscribe for the lifetime of a component; the handlers always see the latest closures. */
export function useProjectEvents(projectId: string | undefined, handlers: ProjectEventHandlers): void {
  const latest = useRef(handlers);
  useEffect(() => {
    latest.current = handlers;
  });
  useEffect(() => {
    if (!projectId) return undefined;
    return subscribeProjectEvents(projectId, {
      onEvent: (event) => latest.current.onEvent?.(event),
      onOpen: () => latest.current.onOpen?.(),
    });
  }, [projectId]);
}
