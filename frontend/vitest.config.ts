import path from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Vitest config for unit/component tests (jsdom). Playwright e2e specs live
// under `e2e/` and are excluded from the Vitest run.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(import.meta.dirname, "./src") },
  },
  test: {
    environment: "./src/test/jsdom-environment.ts",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.{test,spec}.{ts,tsx}", "tests/**/*.test.{ts,tsx}"],
    coverage: {
      provider: "v8",
      reporter: ["text-summary", "json-summary"],
      include: ["src/**/*.{ts,tsx}"],
      // Only what is not worth asserting on: the entry point, generated types, test support.
      exclude: [
        "src/main.tsx",
        "src/api/types.ts",
        "src/test/**",
        "src/vite-env.d.ts",
        "src/**/*.test.{ts,tsx}",
      ],
      // A floor, not a target: statements/branches/functions were 87/86/77 when the gate came in, so the standard's
      // 60% would let the suite lose a quarter of what it covers before anyone noticed. 75 leaves
      // room for an ordinary change and still fails when a feature arrives without tests.
      thresholds: { statements: 75, branches: 75, functions: 75, lines: 75 },
    },
    // Explicit thread pool so parallelism is spec-defined rather than implicit
    // (spec 53 §5.3 / AC10). maxThreads is capped for CI cores.
    pool: "threads",
    poolOptions: {
      threads: {
        minThreads: 1,
        maxThreads: 4,
      },
    },
  },
});
