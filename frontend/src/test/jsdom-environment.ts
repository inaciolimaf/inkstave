/**
 * jsdom with Node's AbortController/AbortSignal.
 *
 * jsdom installs its own abort classes, but `fetch` and `Request` stay Node's, whose undici
 * rejects a foreign signal with "Expected signal to be an instance of AbortSignal" on Node 22.
 * React Router builds a `Request` with a signal on every navigation of a data router, so any test
 * that navigates would crash. In a browser there is one realm and the problem cannot happen.
 */
import { builtinEnvironments, type Environment } from "vitest/environments";

const jsdom = builtinEnvironments.jsdom;

export default <Environment>{
  ...jsdom,
  name: "jsdom-node-abort",
  async setup(global, options) {
    const { AbortController, AbortSignal } = global;
    const environment = await jsdom.setup(global, options);
    Object.assign(global, { AbortController, AbortSignal });
    return environment;
  },
};
