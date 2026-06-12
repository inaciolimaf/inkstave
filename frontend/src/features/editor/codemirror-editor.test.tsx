import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { CodeMirrorEditor } from "./codemirror-editor";
import type { EditorSettings } from "./types";

const settings: EditorSettings = { fontSize: 14, keymap: "default", lineWrapping: true };

describe("CodeMirrorEditor", () => {
  it("mounts a read-only view with the given content", () => {
    const { container } = render(
      <CodeMirrorEditor doc={"\\section{Hi} % note\n$x^2$"} settings={settings} dark={false} />,
    );
    const content = container.querySelector(".cm-content");
    expect(content).toBeTruthy();
    expect(content?.textContent).toContain("section");
    expect(content?.getAttribute("contenteditable")).toBe("false");
    expect(content?.getAttribute("aria-readonly")).toBe("true");
    expect(content?.getAttribute("aria-label")).toBe("LaTeX editor");
  });

  it("renders highlighted LaTeX tokens", () => {
    const { container } = render(
      <CodeMirrorEditor doc={"\\section{Hi}"} settings={settings} dark={false} />,
    );
    // A token span inside the line proves the language + highlighting are wired.
    expect(container.querySelector(".cm-line span")).toBeTruthy();
  });

  it("shows line-number gutter", () => {
    const { container } = render(
      <CodeMirrorEditor doc={"a\nb\nc"} settings={settings} dark={false} />,
    );
    expect(container.querySelector(".cm-gutters")).toBeTruthy();
    expect(container.querySelectorAll(".cm-lineNumbers .cm-gutterElement").length).toBeGreaterThan(
      0,
    );
  });

  it("reconfigures via compartment without recreating the view", async () => {
    function Harness() {
      const [size, setSize] = useState(14);
      return (
        <>
          <button onClick={() => setSize(22)}>grow</button>
          <CodeMirrorEditor
            doc="hello world"
            settings={{ ...settings, fontSize: size }}
            dark={false}
          />
        </>
      );
    }
    const { container } = render(<Harness />);
    const before = container.querySelector(".cm-editor");
    await userEvent.click(screen.getByText("grow"));
    const after = container.querySelector(".cm-editor");
    expect(after).toBe(before); // same DOM node ⇒ the EditorView was not recreated
    expect(container.querySelector(".cm-content")?.textContent).toContain("hello world");
  });
});
