/**
 * jsdom with Node's AbortController/AbortSignal, and jsdom's Web Storage.
 *
 * jsdom installs its own abort classes, but `fetch` and `Request` stay Node's, whose undici
 * rejects a foreign signal with "Expected signal to be an instance of AbortSignal" on Node 22.
 * React Router builds a `Request` with a signal on every navigation of a data router, so any test
 * that navigates would crash. In a browser there is one realm and the problem cannot happen.
 *
 * Node 25 ships its own `localStorage` and `sessionStorage` globals. Without `--localstorage-file`
 * they are empty objects with no `clear` or `getItem`, and Vitest keeps them instead of jsdom's, so
 * every test that touches storage fails. jsdom's window has working ones; they are put back here.
 */
import { builtinEnvironments, type Environment } from "vitest/environments";

const jsdom = builtinEnvironments.jsdom;

const STORAGES = ["localStorage", "sessionStorage"] as const;

function restoreJsdomStorage(global: Record<string, unknown>): void {
  const window = (global.jsdom as { window: Record<string, unknown> }).window;
  for (const name of STORAGES) {
    Object.defineProperty(global, name, {
      value: window[name],
      configurable: true,
      writable: true,
    });
  }
}

export default <Environment>{
  ...jsdom,
  name: "jsdom-node-abort",
  async setup(global, options) {
    const { AbortController, AbortSignal } = global;
    const environment = await jsdom.setup(global, options);
    Object.assign(global, { AbortController, AbortSignal });
    restoreJsdomStorage(global);
    return environment;
  },
};
