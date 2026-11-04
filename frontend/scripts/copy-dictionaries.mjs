// Copies the spell-check dictionaries (spec 113) from their npm packages into public/dictionaries/.
//
// The Hunspell files are large, so they are generated at build time rather than committed. Each
// `.aff` and `.dic` is gzipped (the browser unzips it in the spell worker) and each package's licence
// notice is copied next to it. Runs before `dev` and `build` (see the `pre` scripts in package.json).
import { copyFileSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { gzipSync } from "node:zlib";

const require = createRequire(import.meta.url);
const outDir = join(dirname(fileURLToPath(import.meta.url)), "..", "public", "dictionaries");

/** Language code → npm package that ships its Hunspell dictionary (pinned in package.json). */
const sources = {
  "en-US": "dictionary-en",
  "pt-BR": "dictionary-pt",
};

mkdirSync(outDir, { recursive: true });
for (const [language, pkg] of Object.entries(sources)) {
  // The packages export only their entry point, so the directory comes from it.
  const packageDir = dirname(require.resolve(pkg));
  for (const ext of ["aff", "dic"]) {
    const bytes = readFileSync(join(packageDir, `index.${ext}`));
    writeFileSync(join(outDir, `${language}.${ext}.gz`), gzipSync(bytes, { level: 9 }));
  }
  copyFileSync(join(packageDir, "license"), join(outDir, `${language}.LICENSE.txt`));
}
console.log(`dictionaries: ${Object.keys(sources).join(", ")} written to public/dictionaries`);
