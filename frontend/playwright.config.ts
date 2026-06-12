import { defineConfig, devices } from "@playwright/test";

// Playwright e2e (spec 09): the auth happy-path flow runs against the real Vite
// app with the backend API **mocked via page.route** — no backend, Tectonic, or
// LLM needed, keeping it fast and self-contained. Full journeys arrive in
// spec 54.
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  reporter: "list",
  use: {
    baseURL: "http://localhost:4173",
  },
  webServer: {
    command: "pnpm exec vite --port 4173 --strictPort",
    port: 4173,
    reuseExistingServer: !process.env.CI,
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
