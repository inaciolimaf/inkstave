/**
 * Presence hook (spec 32): publishes the local user's identity + idle flag into
 * Yjs awareness (cursor/selection are auto-published by the y-codemirror.next
 * binding) and exposes the deduplicated list of users currently in the document.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import type { Awareness } from "y-protocols/awareness";

import { colorForUser, colorLight } from "./colors";
import type { CollabDocSession } from "./useCollabDoc";

export const CURSOR_THROTTLE_MS = 50;
export const IDLE_AFTER_MS = 60_000;
export const AWARENESS_TIMEOUT_MS = 30_000;

export interface PresenceUser {
  id: string;
  name: string;
  color: string;
  idle: boolean;
  isLocal: boolean;
}

interface AwarenessUserField {
  id?: string;
  name?: string;
  color?: string;
}

/** Deduplicate awareness states by `user.id`, preferring the local entry. */
export function collectPresence(awareness: Awareness): PresenceUser[] {
  const localClientId = awareness.clientID;
  const byUserId = new Map<string, PresenceUser>();
  for (const [clientId, state] of awareness.getStates()) {
    const user = (state as { user?: AwarenessUserField }).user;
    if (!user || typeof user.id !== "string") continue;
    const presence: PresenceUser = {
      id: user.id,
      name: user.name ?? "Anonymous",
      color: user.color ?? "#888888",
      idle: Boolean((state as { idle?: boolean }).idle),
      isLocal: clientId === localClientId,
    };
    const existing = byUserId.get(user.id);
    if (!existing || (presence.isLocal && !existing.isLocal)) byUserId.set(user.id, presence);
  }
  return [...byUserId.values()];
}

export interface UsePresenceResult {
  users: PresenceUser[];
  markActivity: () => void;
}

export function usePresence(
  session: CollabDocSession | null,
  currentUser: { id: string; name: string } | null,
  options: { idleAfterMs?: number } = {},
): UsePresenceResult {
  const idleAfterMs = options.idleAfterMs ?? IDLE_AFTER_MS;
  const [users, setUsers] = useState<PresenceUser[]>([]);
  const [idle, setIdle] = useState(false);
  const idleTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Publish the local user's identity once per session.
  useEffect(() => {
    if (!session || !currentUser) return;
    const color = colorForUser(currentUser.id);
    session.awareness.setLocalStateField("user", {
      id: currentUser.id,
      name: currentUser.name,
      color,
      colorLight: colorLight(color),
    });
    return () => {
      try {
        session.awareness.setLocalState(null); // clean leave: clears our cursor/avatar
      } catch {
        /* awareness already torn down */
      }
    };
    // Re-publish only when the identity changes, not on every parent re-render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session, currentUser?.id, currentUser?.name]);

  // Publish the idle flag.
  useEffect(() => {
    if (!session) return;
    session.awareness.setLocalStateField("idle", idle);
  }, [idle, session]);

  // Track who is present, reacting to awareness changes (joins/leaves/cursors).
  useEffect(() => {
    if (!session) {
      setUsers([]);
      return;
    }
    const awareness = session.awareness;
    const refresh = () => setUsers(collectPresence(awareness));
    refresh();
    awareness.on("change", refresh);
    return () => awareness.off("change", refresh);
  }, [session]);

  const markActivity = useCallback(() => {
    setIdle(false);
    if (idleTimer.current !== null) clearTimeout(idleTimer.current);
    idleTimer.current = setTimeout(() => setIdle(true), idleAfterMs);
  }, [idleAfterMs]);

  // Arm the idle countdown on mount.
  useEffect(() => {
    markActivity();
    return () => {
      if (idleTimer.current !== null) clearTimeout(idleTimer.current);
    };
  }, [markActivity]);

  return { users, markActivity };
}
