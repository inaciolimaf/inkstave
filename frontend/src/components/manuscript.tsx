/** The root of every screen (spec 106): one sheet, with its header and rules, instead of a stack of cards. */
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

import "./manuscript.css";

// Pilot only: `?face=inter|plex|source` compares the interface typeface on the running screen.
const pilotFace = () => new URLSearchParams(window.location.search).get("face") ?? "source";

export function Manuscript({ bar, children }: { bar?: ReactNode; children: ReactNode }) {
  return (
    <div data-manuscript className="manuscript-root min-h-dvh" data-face={pilotFace()}>
      {bar}
      <main className="mx-auto max-w-3xl px-4 pb-16 pt-8 sm:px-6 sm:pt-14">{children}</main>
    </div>
  );
}

/** What this sheet is, and the one thing to do next. */
export function ManuscriptHeader({ title, actions }: { title: string; actions?: ReactNode }) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-x-6 gap-y-4 pb-4">
      <h1 className="font-serif text-figure font-medium leading-tight tracking-tight">{title}</h1>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </header>
  );
}

export function Rule({ className }: { className?: string }) {
  return <hr className={cn("border-t border-foreground", className)} />;
}
