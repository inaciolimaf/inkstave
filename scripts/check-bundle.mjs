#!/usr/bin/env node
// Fails when the initial JavaScript passes the budget. "Initial" is what index.html makes the
// browser fetch before the app runs: its scripts and its modulepreloads. A chunk loaded on demand
// does not count. Run it after a build: `make web-build web-budget`.
//
// Usage: node scripts/check-bundle.mjs [dist-dir]

import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { gzipSync } from "node:zlib";

const BUDGET_BYTES = 250_000; // 250 KB gzip, decimal.
const REPOSITORY = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const TAG = /<(?:script|link)\b[^>]*>/gi;

function attribute(tag, name) {
  return new RegExp(`\\s${name}=["']?([^"'\\s>]+)`, "i").exec(tag)?.[1];
}

function initialScript(tag) {
  if (/^<script/i.test(tag)) return attribute(tag, "src");
  return attribute(tag, "rel")?.toLowerCase() === "modulepreload" ? attribute(tag, "href") : undefined;
}

function initialScripts(html) {
  const urls = (html.match(TAG) ?? []).map(initialScript).filter(Boolean);
  return [...new Set(urls)];
}

function gzipSize(dist, url) {
  if (/^(?:[a-z]+:)?\/\//i.test(url)) throw new Error(`${url} is not in the bundle, so it cannot be measured`);
  const file = path.join(dist, url.replace(/^\//, "").replace(/[?#].*$/, ""));
  if (!existsSync(file)) throw new Error(`index.html loads ${url}, which is not in ${dist}`);
  return gzipSync(readFileSync(file), { level: 9 }).length;
}

function measure(dist) {
  const index = path.join(dist, "index.html");
  if (!existsSync(index)) throw new Error(`${index} not found: run \`make web-build\` first`);
  const urls = initialScripts(readFileSync(index, "utf-8"));
  if (urls.length === 0) throw new Error(`${index} loads no JavaScript, so nothing was measured`);
  return urls.map((url) => ({ url, size: gzipSize(dist, url) })).sort((a, b) => b.size - a.size);
}

function main() {
  const dist = path.resolve(process.argv[2] ?? path.join(REPOSITORY, "frontend", "dist"));
  const files = measure(dist);
  const total = files.reduce((sum, file) => sum + file.size, 0);
  for (const { url, size } of files) console.log(`${String(size).padStart(9)}  ${url}`);
  console.log(`${String(total).padStart(9)}  total gzip bytes, budget ${BUDGET_BYTES}`);
  if (total > BUDGET_BYTES) throw new Error(`initial JS is ${total - BUDGET_BYTES} bytes over the budget`);
}

try {
  main();
} catch (error) {
  console.error(`check-bundle: ${error.message}`);
  process.exit(1);
}
