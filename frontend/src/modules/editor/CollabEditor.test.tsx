import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { yCollab } from "y-codemirror.next";
import { Awareness } from "y-protocols/awareness";
import * as Y from "yjs";

import type { CollabDocSession, CollabStatus } from "@/modules/collab/useCollabDoc";

import { CollabEditor } from "./CollabEditor";
import type { EditorSettings } from "./types";

const SETTINGS: EditorSettings = { fontSize: 14, keymap: "default", lineWrapping: true };

function makeSession(over: Partial<CollabDocSession> = {}): CollabDocSession {
  const ydoc = new Y.Doc();
  const text = ydoc.getText("content");
  const awareness = new Awareness(ydoc);
  return {
    ydoc,
    text,
    provider: {} as CollabDocSession["provider"],
    awareness,
    status: "connecting" as CollabStatus,
    synced: false,
    cmExtension: yCollab(text, awareness),
    readOnly: false,
    flush: () => Promise.resolve(),
    ...over,
  };
}

const sessions: CollabDocSession[] = [];
afterEach(() => {
  for (const s of sessions) s.ydoc.destroy();
  sessions.length = 0;
});

function track(session: CollabDocSession): CollabDocSession {
  sessions.push(session);
  return session;
}

describe("CollabEditor", () => {
  it("shows a loading state and is not editable until synced (AC6)", () => {
    render(<CollabEditor session={track(makeSession({ synced: false }))} settings={SETTINGS} dark={false} />);
    expect(screen.getByLabelText("Loading document…")).toBeInTheDocument();
    const content = document.querySelector(".cm-content");
    expect(content?.getAttribute("contenteditable")).toBe("false");
  });

  it("shows the new document when the session changes", () => {
    const first = track(makeSession({ synced: true }));
    const second = track(makeSession({ synced: true }));
    first.text.insert(0, "first document");
    second.text.insert(0, "second document");
    const { rerender } = render(<CollabEditor session={first} settings={SETTINGS} dark={false} />);
    expect(document.querySelector(".cm-content")).toHaveTextContent("first document");

    rerender(<CollabEditor session={second} settings={SETTINGS} dark={false} />);
    expect(document.querySelector(".cm-content")).toHaveTextContent("second document");
  });

  it("becomes editable and shows the Live badge after sync (AC1)", () => {
    render(
      <CollabEditor
        session={track(makeSession({ synced: true, status: "connected" }))}
        settings={SETTINGS}
        dark={false}
      />,
    );
    expect(screen.queryByLabelText("Loading document…")).toBeNull();
    expect(screen.getByLabelText("Connection: Live")).toBeInTheDocument();
    const content = document.querySelector(".cm-content");
    expect(content?.getAttribute("contenteditable")).toBe("true");
  });

  it("is non-editable with a 'View only' banner when readOnly (spec 34 AC10)", () => {
    render(
      <CollabEditor
        session={track(makeSession({ synced: true, status: "connected", readOnly: true }))}
        settings={SETTINGS}
        dark={false}
      />,
    );
    const content = document.querySelector(".cm-content");
    expect(content?.getAttribute("contenteditable")).toBe("false");
    expect(screen.getByText("View only")).toBeInTheDocument();
  });
});
