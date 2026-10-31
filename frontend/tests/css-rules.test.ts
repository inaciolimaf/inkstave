import { readdirSync, readFileSync } from "node:fs";

import { expect, it } from "vitest";

// A viewport height that ignores the mobile browser bars; `dvh` is the one that fits.
const STATIC_VIEWPORT_HEIGHT = /100vh|h-screen/;

function offendingLines(path: string): string[] {
  const lines = readFileSync(path, "utf-8").split("\n");
  return lines.flatMap((line, index) =>
    STATIC_VIEWPORT_HEIGHT.test(line) ? [`${path}:${index + 1}: ${line.trim()}`] : [],
  );
}

it("sizes screens with dvh, never 100vh, h-screen or min-h-screen", () => {
  const sources = readdirSync("src", { recursive: true, encoding: "utf-8" })
    .filter((path) => /\.(tsx|css)$/.test(path) && !path.includes(".test.") && !path.startsWith("test/"))
    .map((path) => `src/${path}`);
  expect(sources.flatMap(offendingLines)).toEqual([]);
});

it("draws the edge of every form control with the control-edge token", () => {
  const controls = ["input", "textarea", "select", "switch"];
  const missing = controls.filter(
    (name) => !readFileSync(`src/components/ui/${name}.tsx`, "utf-8").includes("-control-edge"),
  );
  expect(missing).toEqual([]);
});
