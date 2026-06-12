import { InkstaveMark } from "@/components/inkstave-logo";
import { cn } from "@/lib/utils";

// Re-export the shared mark so existing landing imports keep working.
export { InkstaveMark };

/** Mark + serif wordmark, used in the landing nav and footer. */
export function InkstaveWordmark({
  className,
  markClassName,
}: {
  className?: string;
  markClassName?: string;
}) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <InkstaveMark className={cn("h-[1.35em] w-[1.35em]", markClassName)} />
      <span className="font-display text-[1.35rem] font-medium leading-none tracking-tight">
        Inkstave
      </span>
    </span>
  );
}
