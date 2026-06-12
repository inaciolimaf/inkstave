import type { ConflictInfo } from "../api";

export type SaveStatus =
  | "clean" // matches server, nothing pending
  | "dirty" // local edits not yet flushed
  | "saving" // a save request is in flight
  | "error" // last save failed (will retry, or capped)
  | "offline" // no connectivity; queued
  | "conflict"; // server version moved; awaiting user decision

/** Tunable autosave constants (documented in docs/adr/0019). */
export const DEBOUNCE_MS = 1000;
export const RETRY_BACKOFF_MS = [1000, 2000, 4000, 8000];
export const MAX_RETRIES = RETRY_BACKOFF_MS.length;

export interface AutosaveState {
  documentId: string | null;
  baseVersion: number;
  serverText: string;
  localText: string;
  /** The source-of-truth text the editor should show (changes on switch/reload). */
  displayText: string;
  status: SaveStatus;
  lastSavedAt: number | null;
  retryCount: number;
  conflict: ConflictInfo | null;
}
