import { type ReactNode } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "@/auth/auth-context";

function Centered({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center text-muted-foreground">
      {children}
    </div>
  );
}

/** Gate protected routes: redirect to /login when unauthenticated. */
export function RequireAuth() {
  const { isAuthenticated, isBootstrapping } = useAuth();
  const location = useLocation();

  if (isBootstrapping) return <Centered>Loading…</Centered>;
  if (!isAuthenticated) return <Navigate to="/login" state={{ from: location }} replace />;
  return <Outlet />;
}

/** Public-only routes (login/register): redirect authenticated users home. */
export function PublicOnly({ children }: { children: ReactNode }) {
  const { isAuthenticated, isBootstrapping } = useAuth();
  if (isBootstrapping) return <Centered>Loading…</Centered>;
  if (isAuthenticated) return <Navigate to="/" replace />;
  return <>{children}</>;
}
