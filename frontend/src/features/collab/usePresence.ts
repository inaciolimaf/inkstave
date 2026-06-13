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

  // Key the effects on the *awareness instance*, not the `session` wrapper:
  // `useCollabDoc` returns a fresh session object on every parent re-render, so a
  // `[session]` dep would re-run these effects constantly — and the publish
  // cleanup (`setLocalState(null)`) would wipe our presence on each one, after
  // which `setLocalStateField` is a no-op (it bails when the local state is null).
  // The awareness object is stable for the life of the session.
  const awareness = session?.awareness ?? null;

  // Publish the local user's identity once per session. Merge via `setLocalState`
  // (not `setLocalStateField`, which no-ops when the local state is null) so the
  // identity is set regardless of whether the CodeMirror binding has populated a
  // cursor field yet, while preserving any field it did add.
  useEffect(() => {
    if (!awareness || !currentUser) return;
    const color = colorForUser(currentUser.id);
    awareness.setLocalState({
      ...(awareness.getLocalState() ?? {}),
      user: {
        id: currentUser.id,
        name: currentUser.name,
        color,
        colorLight: colorLight(color),
      },
    });
    return () => {
      try {
        awareness.setLocalState(null); // clean leave: clears our cursor/avatar
      } catch {
        /* awareness already torn down */
      }
    };
    // Re-publish only when the identity changes, not on every parent re-render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [awareness, currentUser?.id, currentUser?.name]);

  // Publish the idle flag once a local state exists (the identity effect above
  // creates it); merge to avoid spawning a user-less state.
  useEffect(() => {
    if (!awareness) return;
    const state = awareness.getLocalState();
    if (state !== null) awareness.setLocalState({ ...state, idle });
  }, [idle, awareness]);

  // Track who is present, reacting to awareness changes (joins/leaves/cursors).
  useEffect(() => {
    if (!awareness) {
      setUsers([]);
      return;
    }
    const refresh = () => setUsers(collectPresence(awareness));
    refresh();
    awareness.on("change", refresh);
    return () => awareness.off("change", refresh);
  }, [awareness]);

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
