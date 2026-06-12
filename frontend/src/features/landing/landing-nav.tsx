import { ArrowRight } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { useAuth } from "@/auth/auth-context";
import { cn } from "@/lib/utils";

import { InkstaveWordmark } from "./inkstave-mark";

const LINKS = [
  { href: "#features", key: "nav.features" },
  { href: "#agent", key: "nav.agent" },
  { href: "#collaboration", key: "nav.collaboration" },
  { href: "#faq", key: "nav.faq" },
];

export function LandingNav() {
  const { t } = useTranslation("landing");
  const { isAuthenticated } = useAuth();
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 16);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={cn(
        "fixed inset-x-0 top-0 z-50 transition-all duration-300",
        scrolled
          ? "border-b border-rule/80 bg-paper/85 backdrop-blur-md"
          : "border-b border-transparent",
      )}
    >
      <nav className="mx-auto flex h-16 max-w-6xl items-center gap-6 px-5 sm:px-8">
        <Link to="/" className="text-ink transition-opacity hover:opacity-80">
          <InkstaveWordmark />
        </Link>

        <ul className="ml-2 hidden items-center gap-7 md:flex">
          {LINKS.map((l) => (
            <li key={l.href}>
              <a
                href={l.href}
                className="group relative text-sm text-ink-soft transition-colors hover:text-ink"
              >
                {t(l.key)}
                <span className="absolute -bottom-1 left-0 h-px w-0 bg-ink transition-all duration-300 group-hover:w-full" />
              </a>
            </li>
          ))}
        </ul>

        <div className="ml-auto flex items-center gap-1.5 sm:gap-3">
          {isAuthenticated ? (
            <Link
              to="/projects"
              className="group inline-flex h-9 items-center gap-1.5 rounded-md bg-ink px-4 text-sm font-medium text-paper transition-colors hover:bg-ink/90"
            >
              {t("cta.openApp")}
              <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" />
            </Link>
          ) : (
            <>
              <Link
                to="/login"
                className="hidden h-9 items-center rounded-md px-3 text-sm font-medium text-ink-soft transition-colors hover:text-ink sm:inline-flex"
              >
                {t("cta.signIn")}
              </Link>
              <Link
                to="/register"
                className="group inline-flex h-9 items-center gap-1.5 rounded-md bg-ink px-4 text-sm font-medium text-paper transition-colors hover:bg-ink/90"
              >
                {t("cta.getStarted")}
                <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" />
              </Link>
            </>
          )}
        </div>
      </nav>
    </header>
  );
}
