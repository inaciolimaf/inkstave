// Fails a test when it writes to console.error or console.warn, so React warnings (act, prop types,
// missing accessible descriptions), react-query misuse and missing i18n keys surface where they happen.
// A test that expects a message calls `allowConsole` with its pattern; `ALLOWED` lists the rest.
import { afterEach, beforeEach, expect, vi } from "vitest";
import type { MockInstance } from "vitest";

const LEVELS = ["error", "warn"] as const;
type Level = (typeof LEVELS)[number];

/** Console output the test environment produces on its own. Each entry needs its reason. */
const ALLOWED: readonly RegExp[] = [
  // pdf.js picks its legacy build when it runs under Node-like globals (jsdom); it is a one-off notice.
  /Please use the `legacy` build in Node\.js environments/,
];

let perTest: RegExp[] = [];
let captured: string[] = [];
let spies: MockInstance[] = [];

/** Lets the current test expect a console message that matches `pattern`. Reset after each test. */
export function allowConsole(pattern: RegExp): void {
  perTest.push(pattern);
}

function isTolerated(text: string): boolean {
  return [...ALLOWED, ...perTest].some((pattern) => pattern.test(text));
}

function record(level: Level, args: unknown[]): void {
  const text = args.map((arg) => String(arg)).join(" ");
  if (!isTolerated(text)) {
    captured.push(`console.${level}: ${text}`);
  }
}

/** Registers the per-test hooks; called once from the Vitest setup file. */
export function guardConsole(): void {
  beforeEach(() => {
    perTest = [];
    captured = [];
    spies = LEVELS.map((level) =>
      vi.spyOn(console, level).mockImplementation((...args: unknown[]) => record(level, args)),
    );
  });

  afterEach(() => {
    const unexpected = captured;
    for (const spy of spies) {
      spy.mockRestore();
    }
    spies = [];
    expect(unexpected, "unexpected console output").toEqual([]);
  });
}
