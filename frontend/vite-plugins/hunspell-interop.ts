import { readFile } from "node:fs/promises";

import type { DepOptimizationOptions, Plugin } from "vite";

/** esbuild's plugin type, as Vite re-exposes it (esbuild itself is not a direct dependency). */
type EsbuildPlugin = NonNullable<NonNullable<DepOptimizationOptions["esbuildOptions"]>["plugins"]>[number];

const PACKAGES = /[\\/](hunspell-asm|emscripten-wasm-loader)[\\/]dist[\\/]esm[\\/]/;
const NAMESPACE_IMPORT = /^import \* as (\w+) from ('[^']+');$/gm;

/**
 * hunspell-asm 4.0.2 and emscripten-wasm-loader do `import * as x from "y"` on CommonJS modules that export
 * a function (the Emscripten runtime, nanoid, unixify), then call `x(...)`. Node's interop lets that run;
 * in a Rollup bundle a namespace is not callable, so the spell worker failed with "k is not a function".
 * This rewrites those imports to default imports: in the production bundle (Rollup) and in the dev server's
 * dependency pre-bundling (esbuild), which never runs Rollup plugins (spec 113).
 */
function rewrite(code: string): string {
  return code.replace(NAMESPACE_IMPORT, "import $1 from $2;");
}

export function hunspellInteropFix(): Plugin {
  return {
    name: "inkstave:hunspell-interop",
    enforce: "pre",
    transform(code, id) {
      if (!PACKAGES.test(id) || !code.includes("import * as")) return null;
      return { code: rewrite(code), map: null };
    },
  };
}

export function hunspellInteropEsbuildFix(): EsbuildPlugin {
  return {
    name: "inkstave:hunspell-interop",
    setup(build) {
      build.onLoad({ filter: PACKAGES }, async (args) => ({
        contents: rewrite(await readFile(args.path, "utf-8")),
        loader: "js",
      }));
    },
  };
}
