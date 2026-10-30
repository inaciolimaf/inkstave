/** Shared loading and error states, so screens do not repeat the `isLoading ? ... : isError` ternary. */
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function Loading({ className }: { className?: string }) {
  const { t } = useTranslation("common");
  return (
    <div
      className={cn("flex min-h-screen items-center justify-center text-muted-foreground", className)}
      aria-busy="true"
    >
      {t("state.loading")}
    </div>
  );
}

export function ErrorState({
  message,
  onRetry,
  className,
}: {
  message?: string;
  onRetry: () => void;
  className?: string;
}) {
  const { t } = useTranslation("common");
  return (
    <div className={cn("flex items-center gap-2 text-sm text-destructive", className)} role="alert">
      {message ?? t("state.error")}
      <Button size="sm" variant="outline" onClick={() => onRetry()}>
        {t("action.retry")}
      </Button>
    </div>
  );
}

/** The part of a query result the view reads; fits both `useQuery` and `useInfiniteQuery`. */
interface QueryLike<T> {
  data: T | undefined;
  isLoading: boolean;
  isError: boolean;
  refetch: () => unknown;
}

/** Renders the query's loading state, its error with "retry", or `children` with the data. */
export function QueryView<T>({
  query,
  loading = <Loading />,
  errorMessage,
  errorClassName,
  children,
}: {
  query: QueryLike<T>;
  loading?: ReactNode;
  errorMessage?: string;
  errorClassName?: string;
  children: (data: T) => ReactNode;
}) {
  if (query.isLoading) return <>{loading}</>;
  if (query.isError || query.data === undefined) {
    return (
      <ErrorState message={errorMessage} className={errorClassName} onRetry={() => void query.refetch()} />
    );
  }
  return <>{children(query.data)}</>;
}
