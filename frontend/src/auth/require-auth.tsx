import { type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "@/auth/auth-context";
import { useSetupStatus } from "@/features/setup/useSetupStatus";

function Centered({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center text-muted-foreground">
      {children}
    </div>
  );
}

/**
 * Where an unauthenticated visitor goes: `/setup` on a brand-new deployment
 * (no admin yet), otherwise `/login`. The status call is cheap and cached, so
 * an already-set-up instance pays a single request once per session.
 */
function UnauthenticatedRedirect() {
  const { t } = useTranslation("common");
  const location = useLocation();
  const status = useSetupStatus();
  if (status.isLoading) return <Centered>{t("state.loading")}</Centered>;
  const to = status.data?.needsSetup ? "/setup" : "/login";
  return <Navigate to={to} state={{ from: location }} replace />;
}

/** Gate protected routes: redirect unauthenticated users to setup or login. */
export function RequireAuth() {
  const { t } = useTranslation("common");
  const { isAuthenticated, isBootstrapping } = useAuth();

  if (isBootstrapping) return <Centered>{t("state.loading")}</Centered>;
  if (!isAuthenticated) return <UnauthenticatedRedirect />;
  return <Outlet />;
}

/** Public-only routes (login/register): redirect authenticated users home. */
export function PublicOnly({ children }: { children: ReactNode }) {
  const { t } = useTranslation("common");
  const { isAuthenticated, isBootstrapping } = useAuth();
  if (isBootstrapping) return <Centered>{t("state.loading")}</Centered>;
  // Signed-in users skip public auth pages and go to the app dashboard — NOT "/"
  // which is the public marketing landing, not the signed-in home.
  if (isAuthenticated) return <Navigate to="/projects" replace />;
  return <>{children}</>;
}
