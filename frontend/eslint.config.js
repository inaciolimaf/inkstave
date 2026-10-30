import js from "@eslint/js";
import prettier from "eslint-config-prettier";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import globals from "globals";
import tseslint from "typescript-eslint";

// Files in src/ with a function over the 100-line cap, waiting to be split into named hooks and
// smaller components. The rule stays on for everything else; a new file is born compliant.
// To check how a file will end up: `ESLINT_STRICT=1 pnpm exec eslint <file>`.
const PENDING_SIZE =
  process.env.ESLINT_STRICT === "1"
    ? []
    : [
        "src/features/agent/AgentPanel.tsx",
        "src/features/agent/reducer.ts",
        "src/features/agent/useAgentChat.ts",
        "src/features/auth/ResetPasswordPage.tsx",
        "src/features/diff-review/DiffReviewDialog.tsx",
        "src/features/diff-review/useDiffReview.ts",
        "src/features/editor/autosave/use-document-autosave.ts",
        "src/features/editor/codemirror-editor.tsx",
        "src/features/editor/editor-pane.tsx",
        "src/features/editor/editor-workspace.tsx",
        "src/features/file-tree/file-tree-node.tsx",
        "src/features/file-tree/file-tree-panel.tsx",
        "src/features/landing/agent-demo.tsx",
        "src/features/pdf-preview/PdfToolbar.tsx",
        "src/features/pdf-preview/PreviewPane.tsx",
        "src/features/pdf-preview/hooks/useCompile.ts",
        "src/features/projects/import-project-dialog.tsx",
        "src/features/sharing/MembersList.tsx",
        "src/pages/login.tsx",
        "src/pages/register.tsx",
        "src/pages/setup-page.tsx",
      ];

// What already has a helper or a token is not rewritten by hand. Each group has one allowed file:
// the one that implements the thing.
const HEX_COLOR = "/#([0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})(?![0-9a-zA-Z_-])/";
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
  number: [
    {
      selector: "CallExpression[callee.property.name=/^toLocale(Date|Time)?String$/]",
      message: "Use formatNumber/formatDate/formatDateTime from src/lib/formatting.ts.",
    },
  ],
  sheet: [
    {
      selector: "Literal[value=/shadow-card/]",
      message: "Use <Card> from src/components/ui/card.tsx.",
    },
    {
      selector: "TemplateElement[value.raw=/shadow-card/]",
      message: "Use <Card> from src/components/ui/card.tsx.",
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

export default tseslint.config(
  { ignores: ["dist", "node_modules", "playwright-report", "test-results", "coverage"] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["src/**/*.{ts,tsx}"],
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
    files: ["src/components/ui/**/*.{ts,tsx}", "src/test/**/*.{ts,tsx}"],
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
    },
  },
  ...(PENDING_SIZE.length ? [{ files: PENDING_SIZE, rules: { "max-lines-per-function": "off" } }] : []),
  // Hits that move to their helpers with the feat(frontend) commit that adds those helpers.
  {
    files: ["src/features/collab/colors.ts", "src/features/collab/usePresence.ts"],
    rules: { "no-restricted-syntax": reuseRules("color") },
  },
  {
    files: ["src/features/projects/project-table.tsx"],
    rules: { "no-restricted-syntax": reuseRules("number") },
  },
  {
    files: ["src/features/editor/editor-pane.tsx"],
    rules: { "no-restricted-syntax": reuseRules("keyboard") },
  },
  { files: ["src/lib/palettes.ts"], rules: { "no-restricted-syntax": reuseRules("color") } },
  { files: ["src/lib/formatting.ts"], rules: { "no-restricted-syntax": reuseRules("number") } },
  { files: ["src/components/ui/card.tsx"], rules: { "no-restricted-syntax": reuseRules("sheet") } },
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
