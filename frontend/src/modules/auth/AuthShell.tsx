import type { ComponentProps, ReactNode } from "react";
import { Link } from "react-router-dom";

import { InkstaveLogo } from "@/components/inkstave-logo";
import { Rule, TitlePage } from "@/components/manuscript";
import { cn } from "@/lib/utils";

/**
 * The title page of the sign-in, e-mail and invite flows (spec 106): the form sits directly on the
 * paper. `--input` falls under 3:1 on paper, so a field takes the strong border here.
 */
export function AuthShell({
  title,
  description,
  children,
}: {
  title: string;
  description?: ReactNode;
  children: ReactNode;
}) {
  return (
    <TitlePage>
      <InkstaveLogo className="text-title" />
      <h1 className="mt-8 font-serif text-title font-medium leading-tight tracking-tight">{title}</h1>
      {description && <p className="mt-2 text-body text-muted-foreground">{description}</p>}
      <Rule className="my-6" />
      <div className="[&_input]:border-border-strong">{children}</div>
    </TitlePage>
  );
}

/** A secondary way out of a title page: plain text, underlined so colour is not its only mark. */
export function AuthLink({ className, ...props }: ComponentProps<typeof Link>) {
  return (
    <Link
      className={cn("text-foreground underline underline-offset-4 hover:no-underline", className)}
      {...props}
    />
  );
}

/** The foot of a title page, under the form. */
export function AuthFoot({ children }: { children: ReactNode }) {
  return <p className="mt-6 text-body text-muted-foreground">{children}</p>;
}
