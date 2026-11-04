/**
 * Comment anchors (spec 118, ADR 0118): a range of a document kept as two Yjs relative positions.
 *
 * The start sticks to the character after it (assoc 0), so text typed at the start stays out of the
 * range. The end sticks to the character before it (assoc -1), so text typed at the end stays out too.
 * The server stores both as opaque base64; only this module reads them.
 */
import * as Y from "yjs";

export interface AnchorPair {
  anchorStart: string;
  anchorEnd: string;
}

/** A resolved range in document positions (UTF-16 code units, as CodeMirror counts them). */
export interface ResolvedRange {
  from: number;
  to: number;
}

function toBase64(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

function fromBase64(value: string): Uint8Array {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

/** The anchors for `[from, to)` of a Y.Text. Call it with the text of the open document. */
export function encodeAnchor(text: Y.Text, from: number, to: number): AnchorPair {
  const start = Y.createRelativePositionFromTypeIndex(text, from, 0);
  const end = Y.createRelativePositionFromTypeIndex(text, to, -1);
  return {
    anchorStart: toBase64(Y.encodeRelativePosition(start)),
    anchorEnd: toBase64(Y.encodeRelativePosition(end)),
  };
}

/**
 * The current range of an anchor pair, or `null` when it no longer exists: an unreadable anchor, or one
 * whose end is not after its start (the commented text was deleted, so the anchors collapsed).
 */
export function resolveAnchor(text: Y.Text, anchorStart: string, anchorEnd: string): ResolvedRange | null {
  const doc = text.doc;
  if (!doc) return null;
  try {
    const start = Y.createAbsolutePositionFromRelativePosition(
      Y.decodeRelativePosition(fromBase64(anchorStart)),
      doc,
    );
    const end = Y.createAbsolutePositionFromRelativePosition(
      Y.decodeRelativePosition(fromBase64(anchorEnd)),
      doc,
    );
    if (!start || !end || start.index >= end.index) return null;
    return { from: start.index, to: end.index };
  } catch {
    return null; // an anchor this client cannot read is shown as detached, not as an error
  }
}
