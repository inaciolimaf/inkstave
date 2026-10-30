/** The root of every screen (spec 106): one sheet, with its header and rules, instead of a stack of cards. */
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/** A sheet of the app: `bar` is the edge of the desk, above the text. */
export function Manuscript({ bar, children }: { bar?: ReactNode; children: ReactNode }) {
  return (
    <div data-manuscript className="min-h-dvh">
      {bar}
      <main className="mx-auto max-w-3xl px-4 pb-16 pt-8 sm:px-6 sm:pt-14">{children}</main>
    </div>
  );
}

/** A title page: sign-in, the e-mail flows and error screens, one short centred sheet. */
export function TitlePage({ children, role }: { children: ReactNode; role?: "alert" }) {
  return (
    <main data-manuscript role={role} className="flex min-h-dvh flex-col justify-center px-4 py-10">
      <div className="mx-auto w-full max-w-sm">{children}</div>
    </main>
  );
}

/** The editor's root: the working surface fills the screen, and the sheet sits in the middle of it. */
export function Desk({ bar, children }: { bar: ReactNode; children: ReactNode }) {
  return (
    <div data-manuscript className="flex h-dvh flex-col">
      {bar}
      <main className="flex min-h-0 flex-1 flex-col">{children}</main>
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
