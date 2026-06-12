import { ArrowRight } from "lucide-react";
import type { CSSProperties } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { useAuth } from "@/auth/auth-context";

import { AgentDemo } from "./agent-demo";
import { useReveal } from "./use-reveal";

export function Hero() {
  const { t } = useTranslation("landing");
  const { isAuthenticated } = useAuth();
  const copy = useReveal<HTMLDivElement>();
  const demo = useReveal<HTMLDivElement>();

  // Signed-in visitors go straight to the app; signed-out visitors to login.
  const startHref = isAuthenticated ? "/projects" : "/login";
  const startLabel = isAuthenticated ? t("cta.openApp") : t("cta.startWriting");

  return (
    <section className="relative overflow-hidden pt-32 sm:pt-40">
      {/* Quiet dotted-ledger backdrop, fading toward the page. */}
      <div className="paper-grid pointer-events-none absolute inset-0 [mask-image:radial-gradient(75%_55%_at_50%_30%,black,transparent)]" />
      <div className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-px bg-gradient-to-r from-transparent via-rule to-transparent" />

      <div className="relative mx-auto max-w-6xl px-5 sm:px-8">
        <div ref={copy} className="reveal mx-auto max-w-3xl text-center">
          <span className="mb-6 inline-flex items-center gap-2.5 text-[0.72rem] font-medium uppercase tracking-[0.22em] text-ink-faint">
            <span className="h-px w-6 bg-ink-faint/50" />
            {t("hero.eyebrow")}
            <span className="h-px w-6 bg-ink-faint/50" />
          </span>

          <h1 className="font-display text-[2.7rem] font-normal leading-[1.04] tracking-tight text-ink sm:text-6xl lg:text-[4.4rem]">
            {t("hero.line1")}
            <br className="hidden sm:block" /> {t("hero.line2pre")}{" "}
            <em className="ink-underline italic">{t("hero.emphasis")}</em>
          </h1>

          <p className="mx-auto mt-7 max-w-xl text-balance text-base leading-relaxed text-ink-soft sm:text-lg">
            {t("hero.subhead")}
          </p>

          <div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Link
              to={startHref}
              className="group inline-flex h-11 w-full items-center justify-center gap-2 rounded-md bg-ink px-7 text-sm font-medium text-paper shadow-[0_12px_30px_-12px_hsl(var(--ink)/0.6)] transition-all hover:bg-ink/90 hover:shadow-[0_16px_36px_-12px_hsl(var(--ink)/0.7)] sm:w-auto"
            >
              {startLabel}
              <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" />
            </Link>
            <a
              href="#agent"
              className="inline-flex h-11 w-full items-center justify-center gap-2 rounded-md border border-rule bg-paper/60 px-7 text-sm font-medium text-ink transition-colors hover:bg-paper-deep sm:w-auto"
            >
              {t("cta.seeAgent")}
            </a>
          </div>

          <p className="mt-6 flex flex-wrap items-center justify-center gap-x-5 gap-y-2 text-xs text-ink-faint">
            <span>{t("hero.trust1")}</span>
            <span className="hidden h-3 w-px bg-rule sm:inline-block" />
            <span>{t("hero.trust2")}</span>
          </p>
        </div>

        {/* The scripted agent demo, raised on a paper plinth. */}
        <div
          ref={demo}
          className="reveal mt-16 sm:mt-20"
          style={{ "--reveal-delay": "120ms" } as CSSProperties}
        >
          <div className="relative mx-auto max-w-4xl">
            <div className="pointer-events-none absolute -inset-x-6 -bottom-6 top-8 -z-10 rounded-[1.6rem] bg-paper-deeper/70 [mask-image:linear-gradient(black,transparent)]" />
            <div className="rounded-2xl border border-rule bg-paper-deep/40 p-2.5 shadow-[0_40px_80px_-50px_hsl(var(--ink)/0.55)] sm:p-3.5">
              <AgentDemo />
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
