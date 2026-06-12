import "./landing.css";

import { AgentShowcase } from "./agent-showcase";
import { Collaboration } from "./collaboration";
import { Faq } from "./faq";
import { FeatureGrid } from "./feature-grid";
import { ClosingCta, LandingFooter } from "./footer";
import { Hero } from "./hero";
import { LandingNav } from "./landing-nav";

/**
 * Public marketing page served at `/`. Self-contained under `.landing-root`,
 * which carries the "ink on paper" palette and serif display type so the
 * marketing surface can have its own voice without touching the app shell.
 *
 * Copy comes from the `landing` i18n namespace: English by default, Portuguese
 * when the visitor's browser language is Portuguese (see src/i18n/config.ts).
 */
export function LandingPage() {
  return (
    <div className="landing-root min-h-screen antialiased">
      <LandingNav />
      <main>
        <Hero />
        <FeatureGrid />
        <AgentShowcase />
        <Collaboration />
        <Faq />
        <ClosingCta />
      </main>
      <LandingFooter />
    </div>
  );
}
