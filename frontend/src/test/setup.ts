// Global Vitest setup: extends `expect` with jest-dom matchers so component
// tests (added from spec 09 onwards) can assert on the DOM.
import "@testing-library/jest-dom/vitest";
import { cleanup, configure } from "@testing-library/react";
import { afterEach } from "vitest";

import { guardConsole } from "@/test/console-guard";

// Initialise the global i18n instance so components using useTranslation render
// real (English, in jsdom) copy under test rather than raw keys.
import i18n from "@/i18n/config";

// Async queries (findBy, waitFor) get a generous deadline: CI runners are slower than a laptop.
configure({ asyncUtilTimeout: 3000 });

// A missing i18n key is a bug: report it as console output, which guardConsole turns into a failure.
i18n.options.saveMissing = true;
i18n.options.missingKeyHandler = (_lngs, namespace, key) => {
  console.warn(`missing i18n key: ${namespace}:${key}`);
};

guardConsole();

// Globals are off (vitest.config.ts), so testing-library cannot register its own cleanup. Vitest runs
// afterEach hooks in reverse registration order: this one must come after guardConsole's, so the DOM is
// unmounted even when the console check fails the test.
afterEach(() => cleanup());

// jsdom lacks the pointer-capture / scroll APIs that Radix primitives (Dialog,
// DropdownMenu, Select) call. Polyfill them as no-ops so those components work
// under test.
const proto = window.Element.prototype as unknown as Record<string, unknown>;
proto.hasPointerCapture ??= () => false;
proto.setPointerCapture ??= () => {};
proto.releasePointerCapture ??= () => {};
proto.scrollIntoView ??= () => {};

// jsdom has no canvas 2d context; the PDF.js viewer guards on a null context,
// but jsdom's getContext throws + logs. Return null quietly instead.
const canvasProto = window.HTMLCanvasElement.prototype as unknown as Record<string, unknown>;
canvasProto.getContext = () => null;

// jsdom lacks Range geometry that CodeMirror's measuring touches.
const rangeProto = window.Range.prototype as unknown as Record<string, unknown>;
rangeProto.getClientRects = () => ({ length: 0, item: () => null }) as unknown as DOMRectList;
rangeProto.getBoundingClientRect = () =>
  ({ x: 0, y: 0, width: 0, height: 0, top: 0, left: 0, right: 0, bottom: 0 }) as DOMRect;

// react-resizable-panels needs ResizeObserver; CodeMirror reads matchMedia.
const win = window as unknown as Record<string, unknown>;
if (!win.ResizeObserver) {
  win.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}
if (!window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: true,
    media: query,
    onchange: null,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
    dispatchEvent() {
      return false;
    },
  })) as unknown as typeof window.matchMedia;
}
