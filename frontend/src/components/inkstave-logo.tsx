import { cn } from "@/lib/utils";

/**
 * The Inkstave brand mark: a fountain-pen nib (ink) resting on a ruled baseline
 * (a "stave"). Line-art in `currentColor`, so it inherits colour from context
 * and stays crisp at any size. Shared by the app shell and the landing page.
 */
export function InkstaveMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 28" fill="none" aria-hidden="true" className={cn("h-6 w-6", className)}>
      <g stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 3 L17.5 14 L12 20 L6.5 14 Z" />
        <path d="M12 8 V18" />
        <path d="M5 24 H19" />
      </g>
      <circle cx="12" cy="9.2" r="1.05" fill="currentColor" />
    </svg>
  );
}

/**
 * Mark + serif wordmark — the app-wide logo. The serif (Newsreader, via the
 * global `font-serif` utility) ties the app's brand to the landing page.
 */
export function InkstaveLogo({
  className,
  markClassName,
}: {
  className?: string;
  markClassName?: string;
}) {
  // Both mark and wordmark are sized in `em`, so the whole logo scales with the
  // wrapper's font-size — override it via `className` (e.g. `text-2xl`).
  return (
    <span
      className={cn(
        "inline-flex select-none items-center gap-2 text-[1.2rem] text-foreground",
        className,
      )}
    >
      <InkstaveMark className={cn("h-[1.3em] w-[1.3em]", markClassName)} />
      <span className="font-serif text-[1em] font-medium leading-none tracking-tight">
        Inkstave
      </span>
    </span>
  );
}
