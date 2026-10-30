import type { Config } from "tailwindcss";
import animate from "tailwindcss-animate";

export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: { "2xl": "1400px" },
    },
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        success: {
          DEFAULT: "hsl(var(--success))",
          on: "hsl(var(--on-success))",
          soft: "hsl(var(--success-soft))",
          text: "hsl(var(--success-text))",
        },
        warning: {
          DEFAULT: "hsl(var(--warning))",
          on: "hsl(var(--on-warning))",
          soft: "hsl(var(--warning-soft))",
          text: "hsl(var(--warning-text))",
        },
        error: {
          soft: "hsl(var(--error-soft))",
          text: "hsl(var(--error-text))",
        },
        focus: "hsl(var(--focus))",
        "border-strong": "hsl(var(--border-strong))",
        backdrop: "hsl(var(--backdrop))",
        page: "hsl(var(--page))",
        // Landing-only "ink on paper" palette. The tokens are defined inside
        // `.landing-root` (see modules/landing/landing.css), so these utilities
        // resolve only on the marketing page and never touch the app shell.
        paper: {
          DEFAULT: "hsl(var(--paper))",
          deep: "hsl(var(--paper-deep))",
          deeper: "hsl(var(--paper-deeper))",
        },
        ink: {
          DEFAULT: "hsl(var(--ink))",
          soft: "hsl(var(--ink-soft))",
          faint: "hsl(var(--ink-faint))",
        },
        rule: "hsl(var(--rule))",
      },
      // Extra families used only on the landing (applied via `font-serif` /
      // `font-mono`). `sans` is intentionally left as the Tailwind default so
      // the existing app keeps its system font stack.
      fontFamily: {
        serif: ['"Newsreader Variable"', "Georgia", "Cambria", "serif"],
        mono: ['"JetBrains Mono Variable"', "ui-monospace", "SFMono-Regular", "monospace"],
      },
      fontSize: {
        small: "var(--text-small)",
        body: "var(--text-body)",
        heading: "var(--text-heading)",
        title: "var(--text-title)",
        figure: "var(--text-figure)",
      },
      transitionDuration: {
        fast: "var(--motion-fast)",
        base: "var(--motion-base)",
        slow: "var(--motion-slow)",
      },
      transitionTimingFunction: {
        out: "var(--ease-out)",
        "in-out": "var(--ease-in-out)",
      },
      height: { dvh: "100dvh" },
      minHeight: { dvh: "100dvh" },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
    },
  },
  plugins: [animate],
} satisfies Config;
