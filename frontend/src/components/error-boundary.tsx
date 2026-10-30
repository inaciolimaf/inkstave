/** App-root React error boundary (spec 64): a friendly fallback, never a white screen. */
import { Component, type ErrorInfo, type ReactNode } from "react";

import { ErrataSlip } from "@/components/states";
import { Button } from "@/components/ui/button";
// Use the i18n instance directly (not the useTranslation hook): the fallback may
// render when the surrounding tree is unhealthy, so we avoid extra hook context.
import i18n from "@/i18n/config";

interface Props {
  children: ReactNode;
  /** Optional custom fallback; defaults to {@link DefaultFallback}. */
  fallback?: (reset: () => void) => ReactNode;
}

interface State {
  hasError: boolean;
}

// eslint-disable-next-line react-refresh/only-export-components -- helper for the class boundary below
function DefaultFallback({ onReset }: { onReset: () => void }) {
  return (
    <ErrataSlip
      title={i18n.t("common:errorBoundary.title")}
      body={i18n.t("common:errorBoundary.body")}
      actions={
        <>
          <Button onClick={onReset}>{i18n.t("common:errorBoundary.retry")}</Button>
          <Button variant="outline" onClick={() => window.location.reload()}>
            {i18n.t("common:errorBoundary.reload")}
          </Button>
        </>
      }
    />
  );
}

/**
 * Catches render-time errors in the descendant tree and renders a fallback
 * instead of letting React unmount the whole app (a blank page). Hand-rolled
 * (no `react-error-boundary` dependency) per spec 64.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Surface for diagnostics; a real deployment would forward this to telemetry.
    console.error("Uncaught render error:", error, info.componentStack);
  }

  private reset = (): void => this.setState({ hasError: false });

  render(): ReactNode {
    if (this.state.hasError) {
      return this.props.fallback ? this.props.fallback(this.reset) : <DefaultFallback onReset={this.reset} />;
    }
    return this.props.children;
  }
}
