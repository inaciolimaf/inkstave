import { ArrowRight, Github } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { useAuth } from "@/auth/auth-context";

import { InkstaveWordmark } from "./inkstave-mark";
import { useReveal } from "./use-reveal";

export function ClosingCta() {
  const { t } = useTranslation("landing");
  const { isAuthenticated } = useAuth();
  const ref = useReveal<HTMLDivElement>();

  // Same auth logic as the hero CTA: signed-in → app, signed-out → sign in.
  const primaryHref = isAuthenticated ? "/projects" : "/login";
  const primaryLabel = isAuthenticated ? t("cta.openApp") : t("cta.startWritingFree");

  return (
    <section className="px-5 pb-24 pt-4 sm:px-8 sm:pb-32">
      <div
        ref={ref}
        className="reveal relative mx-auto max-w-5xl overflow-hidden rounded-3xl bg-ink px-6 py-16 text-center sm:px-12 sm:py-24"
      >
        {/* faint ledger texture on the dark band */}
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.07]"
          style={{
            backgroundImage:
              "repeating-linear-gradient(to bottom, transparent 0, transparent 31px, white 31px, white 32px)",
          }}
        />
        <div className="relative">
          <h2 className="mx-auto max-w-2xl font-display text-3xl font-normal leading-[1.1] tracking-tight text-paper sm:text-5xl">
            {t("footer.ctaTitle")}
          </h2>
          <p className="mx-auto mt-5 max-w-md text-base leading-relaxed text-paper/70">
            {t("footer.ctaBody")}
          </p>
          <div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Link
              to={primaryHref}
              className="group inline-flex h-11 w-full items-center justify-center gap-2 rounded-md bg-paper px-7 text-sm font-medium text-ink transition-transform hover:scale-[1.02] sm:w-auto"
            >
              {primaryLabel}
              <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" />
            </Link>
            {!isAuthenticated && (
              <Link
                to="/register"
                className="inline-flex h-11 w-full items-center justify-center rounded-md border border-paper/25 px-7 text-sm font-medium text-paper transition-colors hover:bg-paper/10 sm:w-auto"
              >
                {t("cta.createAccount")}
              </Link>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

const COLUMNS = [
  {
    headingKey: "footer.colProduct",
    links: [
      { key: "nav.features", href: "#features" },
      { key: "nav.agent", href: "#agent" },
      { key: "nav.collaboration", href: "#collaboration" },
      { key: "nav.faq", href: "#faq" },
    ],
  },
  {
    headingKey: "footer.colResources",
    links: [
      { key: "footer.linkDocumentation", href: "#" },
      { key: "footer.linkChangelog", href: "#" },
      { key: "footer.linkStatus", href: "#" },
    ],
  },
  {
    headingKey: "footer.colProject",
    links: [
      { key: "footer.linkGithub", href: "#" },
      { key: "footer.linkLicense", href: "#" },
      { key: "footer.linkSelfHost", href: "#" },
    ],
  },
];

export function LandingFooter() {
  const { t } = useTranslation("landing");

  return (
    <footer className="border-t border-rule bg-paper">
      <div className="mx-auto max-w-6xl px-5 py-16 sm:px-8">
        <div className="grid gap-12 sm:grid-cols-2 lg:grid-cols-[1.5fr_1fr_1fr_1fr]">
          <div className="max-w-xs">
            <InkstaveWordmark />
            <p className="mt-4 max-w-[14rem] font-display text-[0.95rem] italic leading-relaxed text-ink-soft">
              {t("footer.tagline")}
            </p>
            <a
              href="#"
              className="mt-5 inline-flex items-center gap-2 rounded-md border border-rule px-3 py-1.5 text-sm text-ink-soft transition-colors hover:border-ink/30 hover:text-ink"
            >
              <Github className="size-4" /> {t("footer.star")}
            </a>
          </div>

          {COLUMNS.map((col) => (
            <div key={col.headingKey}>
              <h3 className="text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-ink-faint">
                {t(col.headingKey)}
              </h3>
              <ul className="mt-4 space-y-2.5">
                {col.links.map((l) => (
                  <li key={l.key}>
                    <a
                      href={l.href}
                      className="text-sm text-ink-soft transition-colors hover:text-ink"
                    >
                      {t(l.key)}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-14 flex flex-col items-center justify-between gap-3 border-t border-rule pt-6 text-xs text-ink-faint sm:flex-row">
          <p>{t("footer.copyright", { year: new Date().getFullYear() })}</p>
          <p className="font-mono">{t("footer.typeset")}</p>
        </div>
      </div>
    </footer>
  );
}
