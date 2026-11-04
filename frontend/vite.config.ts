import path from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

import { hunspellInteropEsbuildFix, hunspellInteropFix } from "./vite-plugins/hunspell-interop";

export default defineConfig({
  plugins: [react()],
  // The spell worker is bundled on its own; it needs the hunspell-asm fix (spec 113).
  worker: { format: "es", plugins: () => [hunspellInteropFix()] },
  optimizeDeps: { esbuildOptions: { plugins: [hunspellInteropEsbuildFix()] } },
  resolve: {
    alias: { "@": path.resolve(import.meta.dirname, "./src") },
  },
});
