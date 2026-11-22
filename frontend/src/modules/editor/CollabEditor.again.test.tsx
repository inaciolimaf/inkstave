/**
 * "Do it again" lifecycle tests for the collab editor: switching documents A -> B -> A must
 * show the text of the document on screen each time, whether the session is new or reused.
 */
import { renderWithProviders as render } from "@/test/utils";
import { afterEach, describe, expect, it } from "vitest";
import { yCollab } from "y-codemirror.next";
import { Awareness } from "y-protocols/awareness";
import * as Y from "yjs";

import { SuggestController } from "@/modules/collab/suggestions";
import type { CollabDocSession, CollabStatus } from "@/modules/collab/useCollabDoc";

import { CollabEditor } from "./CollabEditor";
import type { EditorSettings } from "./types";

const SETTINGS: EditorSettings = { fontSize: 14, keymap: "default", lineWrapping: true, autocomplete: true };

function makeSession(text: string): CollabDocSession {
  const ydoc = new Y.Doc();
  const ytext = ydoc.getText("content");
  ytext.insert(0, text);
  const awareness = new Awareness(ydoc);
  return {
    projectId: "p1",
    ydoc,
    text: ytext,
    provider: {} as CollabDocSession["provider"],
    awareness,
    status: "connected" as CollabStatus,
    synced: true,
    cmExtension: yCollab(ytext, awareness),
    readOnly: false,
    suggest: new SuggestController(() => null, awareness),
    flush: () => Promise.resolve(),
  };
}

const made: CollabDocSession[] = [];
afterEach(() => {
  for (const s of made.splice(0)) s.ydoc.destroy();
});

function session(text: string): CollabDocSession {
  const s = makeSession(text);
  made.push(s);
  return s;
}

const shown = () => document.querySelector(".cm-content")?.textContent ?? "";

describe("CollabEditor, do it again", () => {
  it("shows A, then B, then A again, each with its own text", () => {
    const a = session("document A text");
    const b = session("document B text");
    const { rerender } = render(<CollabEditor session={a} settings={SETTINGS} dark={false} />);
    expect(shown()).toBe("document A text");

    rerender(<CollabEditor session={b} settings={SETTINGS} dark={false} />);
    expect(shown()).toBe("document B text");

    rerender(<CollabEditor session={a} settings={SETTINGS} dark={false} />);
    expect(shown()).toBe("document A text");
  });

  it("follows edits made to each document after coming back to it", () => {
    const a = session("first");
    const b = session("second");
    const { rerender } = render(<CollabEditor session={a} settings={SETTINGS} dark={false} />);
    rerender(<CollabEditor session={b} settings={SETTINGS} dark={false} />);
    rerender(<CollabEditor session={a} settings={SETTINGS} dark={false} />);

    a.text.insert(a.text.length, " edited");
    expect(shown()).toBe("first edited");
    b.text.insert(0, "B ");
    expect(shown()).toBe("first edited");
  });

  it("A to B to A with a freshly opened session for A shows the new session's text", () => {
    const a1 = session("A version one");
    const b = session("B");
    const { rerender } = render(<CollabEditor session={a1} settings={SETTINGS} dark={false} />);
    rerender(<CollabEditor session={b} settings={SETTINGS} dark={false} />);

    const a2 = session("A version two");
    rerender(<CollabEditor session={a2} settings={SETTINGS} dark={false} />);
    expect(shown()).toBe("A version two");
  });
});
