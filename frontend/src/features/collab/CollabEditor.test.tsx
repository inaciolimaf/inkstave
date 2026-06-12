import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { yCollab } from "y-codemirror.next";
import { Awareness } from "y-protocols/awareness";
import * as Y from "yjs";

import type { EditorSettings } from "@/features/editor/types";

import { CollabEditor } from "./CollabEditor";
import type { CollabDocSession, CollabStatus } from "./useCollabDoc";

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
    render(
      <CollabEditor
        session={track(makeSession({ synced: false }))}
        settings={SETTINGS}
        dark={false}
      />,
    );
    expect(screen.getByLabelText("Loading document…")).toBeInTheDocument();
    const content = document.querySelector(".cm-content");
    expect(content?.getAttribute("contenteditable")).toBe("false");
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
