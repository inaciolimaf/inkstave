// Global Vitest setup: extends `expect` with jest-dom matchers so component
// tests (added from spec 09 onwards) can assert on the DOM.
import "@testing-library/jest-dom";

// jsdom lacks the pointer-capture / scroll APIs that Radix primitives (Dialog,
// DropdownMenu, Select) call. Polyfill them as no-ops so those components work
// under test.
const proto = window.Element.prototype as unknown as Record<string, unknown>;
proto.hasPointerCapture ??= () => false;
proto.setPointerCapture ??= () => {};
proto.releasePointerCapture ??= () => {};
proto.scrollIntoView ??= () => {};

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
