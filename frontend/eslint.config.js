import { readdirSync } from "node:fs";

import js from "@eslint/js";
import prettier from "eslint-config-prettier";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import globals from "globals";
import tseslint from "typescript-eslint";

// What already has a helper or a token is not rewritten by hand. Each group has one allowed file:
// the one that implements the thing.
const HEX_COLOR = "/#([0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})(?![0-9a-zA-Z_-])/";
const RAW_PALETTE =
  "/(^|[\\s:])(bg|text|border|ring|fill|stroke)-(white|black|(red|rose|orange|amber|yellow|green|emerald|teal|sky|blue|indigo|violet|purple|pink|gray|slate|zinc|neutral|stone)-[0-9]+)/";
const RAW_TYPE = "/(^|[\\s:])text-(xs|sm|base|lg|xl|[2-9]xl|\\[[0-9.]+(px|rem)\\])(\\s|$)/";
const REUSE_RULES = {
  color: [
    {
      selector: `Literal[value=${HEX_COLOR}]`,
      message: "Use a design token; fixed content colours live in src/lib/palettes.ts.",
    },
    {
      selector: `TemplateElement[value.raw=${HEX_COLOR}]`,
      message: "Use a design token; fixed content colours live in src/lib/palettes.ts.",
    },
  ],
  palette: [
    {
      selector: `Literal[value=${RAW_PALETTE}]`,
      message: "Use a role token (success, warning, error-text, backdrop, page) instead of a Tailwind hue.",
    },
    {
      selector: `TemplateElement[value.raw=${RAW_PALETTE}]`,
      message: "Use a role token (success, warning, error-text, backdrop, page) instead of a Tailwind hue.",
    },
  ],
  type: [
    {
      selector: `Literal[value=${RAW_TYPE}]`,
      message: "Use a type token: text-small, text-body, text-heading, text-title or text-figure.",
    },
    {
      selector: `TemplateElement[value.raw=${RAW_TYPE}]`,
      message: "Use a type token: text-small, text-body, text-heading, text-title or text-figure.",
    },
  ],
  number: [
    {
      selector: "CallExpression[callee.property.name=/^toLocale(Date|Time)?String$/]",
      message: "Use formatNumber/formatDate/formatDateTime from src/lib/formatting.ts.",
    },
  ],
  keyboard: [
    {
      selector: "CallExpression[callee.property.name='addEventListener'][arguments.0.value='keydown']",
      message: "Use useShortcuts from src/lib/shortcuts.ts.",
    },
  ],
};

/** The reuse rules for src/, minus those of the group the file implements. */
function reuseRules(...allowed) {
  const groups = Object.entries(REUSE_RULES).filter(([name]) => !allowed.includes(name));
  return ["error", ...groups.flatMap(([, rules]) => rules)];
}

// A module imports another only through its index.ts. A pattern on `modules/**` would not catch a
// relative `../other/x`, so that case is a regex built from the folder list.
const MODULES = readdirSync("src/modules");
const BOUNDARY_MESSAGE = "Import another module through its index.ts (`@/modules/<name>`).";
const MODULE_BOUNDARY = {
  patterns: [
    { group: ["@/modules/*/**"], message: BOUNDARY_MESSAGE },
    { regex: `^(\\.\\./)+(${MODULES.join("|")})(/|$)`, message: BOUNDARY_MESSAGE },
  ],
};
const NO_MODULES = {
  patterns: [{ group: ["@/modules", "@/modules/**"], message: "Shared code cannot depend on a module." }],
};

export default tseslint.config(
  { ignores: ["dist", "node_modules", "playwright-report", "test-results", "coverage", "src/api/types.ts"] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["src/**/*.{ts,tsx}", "tests/**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-hooks/exhaustive-deps": "error",
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
    },
  },
  {
    // Vendored shadcn/ui primitives export variants/hooks alongside components;
    // fast-refresh granularity is irrelevant for these leaf files.
    files: [
      "src/components/ui/**/*.{ts,tsx}",
      "src/test/**/*.{ts,tsx}",
      "tests/**/*.{ts,tsx}",
      "src/router.tsx",
    ],
    rules: { "react-refresh/only-export-components": "off" },
  },
  {
    // Tests stay out of the size cap and the reuse rules: a `describe` is long by nature.
    files: ["src/**/*.{ts,tsx}"],
    ignores: ["src/**/*.test.{ts,tsx}", "src/test/**"],
    rules: {
      "max-lines-per-function": ["error", { max: 100, skipBlankLines: true, skipComments: true }],
      "max-lines": ["error", { max: 300, skipBlankLines: true, skipComments: true }],
      "no-restricted-syntax": reuseRules(),
      "no-restricted-imports": ["error", MODULE_BOUNDARY],
    },
  },
  {
    files: ["src/components/**/*.{ts,tsx}", "src/lib/**/*.{ts,tsx}", "src/i18n/**/*.{ts,tsx}"],
    ignores: ["src/**/*.test.{ts,tsx}"],
    rules: { "no-restricted-imports": ["error", NO_MODULES] },
  },
  // The landing is a marketing page with its own display sizes (spec 106).
  {
    files: ["src/modules/landing/**/*.{ts,tsx}"],
    ignores: ["src/**/*.test.{ts,tsx}"],
    rules: { "no-restricted-syntax": reuseRules("type") },
  },
  { files: ["src/lib/palettes.ts"], rules: { "no-restricted-syntax": reuseRules("color") } },
  { files: ["src/lib/formatting.ts"], rules: { "no-restricted-syntax": reuseRules("number") } },
  { files: ["src/lib/shortcuts.ts"], rules: { "no-restricted-syntax": reuseRules("keyboard") } },
  {
    // Playwright e2e suite (spec 54): Node + browser globals. No React rules: Playwright's fixture
    // callback is named `use`, which the hooks plugin would mistake for React's `use`.
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["e2e/**/*.ts", "playwright.config.ts"],
    languageOptions: {
      ecmaVersion: 2022,
      globals: { ...globals.node, ...globals.browser },
    },
  },
  prettier,
);
