import { type ReactNode, useId } from "react";

import { Rule } from "@/components/manuscript";

/** A section of the front matter: a serif title over a ruled body. */
export function SettingsSection({
  title,
  description,
  children,
}: {
  title: string;
  description?: ReactNode;
  children: ReactNode;
}) {
  const headingId = useId();
  return (
    <section aria-labelledby={headingId}>
      <h2 id={headingId} className="font-serif text-title font-medium">
        {title}
      </h2>
      <Rule className="mb-4 mt-2 border-border" />
      {description && <p className="mb-4 text-body text-muted-foreground">{description}</p>}
      {children}
    </section>
  );
}
