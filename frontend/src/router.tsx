import { Navigate, type RouteObject, createBrowserRouter, createMemoryRouter } from "react-router-dom";

import { RouteError } from "@/components/route-error";
import { Loading } from "@/components/states";
import { RequireAuth } from "@/modules/auth";
import { ConfirmEmailRoute } from "@/routes/confirm-email";
import { EditorRoute } from "@/routes/editor";
import { ForgotPasswordRoute } from "@/routes/forgot-password";
import { InviteRoute } from "@/routes/invite";
import { LandingRoute } from "@/routes/landing";
import { LoginRoute } from "@/routes/login";
import { MagicLinkRoute } from "@/routes/magic-link";
import { ProjectsRoute } from "@/routes/projects";
import { RegisterRoute } from "@/routes/register";
import { ResendVerificationRoute } from "@/routes/resend-verification";
import { ResetPasswordRoute } from "@/routes/reset-password";
import { SettingsRoute } from "@/routes/settings";
import { SetupRoute } from "@/routes/setup";
import { VerifyEmailRoute } from "@/routes/verify-email";

const ROUTES: RouteObject[] = [
  // Public marketing landing page (reachable signed-out).
  { path: "/", element: <LandingRoute /> },
  // First-run admin creation; public (reachable signed-out, no setup gate itself).
  { path: "/setup", element: <SetupRoute /> },
  { path: "/login", element: <LoginRoute /> },
  { path: "/register", element: <RegisterRoute /> },
  // Token-authorized; reachable signed-out (the token alone authorizes the change).
  { path: "/settings/confirm-email", element: <ConfirmEmailRoute /> },
  // Email link-based auth flows (spec 104). The token-authorized callbacks are
  // reachable even while signed in (a user may click a link in another tab), so
  // they are NOT wrapped in PublicOnly; only the pure request pages are.
  { path: "/verify-email", element: <VerifyEmailRoute /> },
  { path: "/verify-email/resend", element: <ResendVerificationRoute /> },
  { path: "/magic-link", element: <MagicLinkRoute /> },
  { path: "/reset-password", element: <ResetPasswordRoute /> },
  { path: "/forgot-password", element: <ForgotPasswordRoute /> },
  {
    element: <RequireAuth />,
    children: [
      { path: "/projects", element: <ProjectsRoute /> },
      { path: "/projects/:projectId", element: <EditorRoute /> },
      { path: "/settings", element: <SettingsRoute /> },
      { path: "/invite/:token", element: <InviteRoute /> },
    ],
  },
  { path: "*", element: <Navigate to="/projects" replace /> },
];

/** Every route sits under one root, so an error or a lazy load gets the app's own screens. */
const ROOT: RouteObject = {
  ErrorBoundary: RouteError,
  HydrateFallback: Loading,
  children: ROUTES,
};

/** The app's router; `initialEntries` gives a memory history, which is what the tests use. */
export function createAppRouter(initialEntries?: string[]) {
  return initialEntries ? createMemoryRouter([ROOT], { initialEntries }) : createBrowserRouter([ROOT]);
}

function collectPaths(routes: RouteObject[]): string[] {
  return routes.flatMap((route) => [
    ...(route.path ? [route.path] : []),
    ...collectPaths(route.children ?? []),
  ]);
}

/** Every path the app declares; the e2e route list is checked against it. */
export const ROUTE_PATHS = collectPaths(ROUTES);
