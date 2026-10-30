import { Navigate, type RouteObject, createBrowserRouter, createMemoryRouter } from "react-router-dom";

import { PublicOnly, RequireAuth } from "@/auth/require-auth";
import { RouteError } from "@/components/route-error";
import { Loading } from "@/components/states";
import { ForgotPasswordPage } from "@/features/auth/ForgotPasswordPage";
import { MagicLinkPage } from "@/features/auth/MagicLinkPage";
import { ResendVerificationPage } from "@/features/auth/ResendVerificationPage";
import { ResetPasswordPage } from "@/features/auth/ResetPasswordPage";
import { VerifyEmailPage } from "@/features/auth/VerifyEmailPage";
import { LandingPage } from "@/features/landing/landing-page";
import { ProjectsPage } from "@/features/projects/projects-page";
import { ConfirmEmailPage } from "@/features/settings/ConfirmEmailPage";
import { SettingsPage } from "@/features/settings/SettingsPage";
import { AcceptInvitePage } from "@/features/sharing/AcceptInvitePage";
import { EditorPage } from "@/pages/editor";
import { LoginPage } from "@/pages/login";
import { RegisterPage } from "@/pages/register";
import { SetupPage } from "@/pages/setup-page";

const ROUTES: RouteObject[] = [
  // Public marketing landing page (reachable signed-out).
  { path: "/", element: <LandingPage /> },
  // First-run admin creation; public (reachable signed-out, no setup gate itself).
  { path: "/setup", element: <SetupPage /> },
  {
    path: "/login",
    element: (
      <PublicOnly>
        <LoginPage />
      </PublicOnly>
    ),
  },
  {
    path: "/register",
    element: (
      <PublicOnly>
        <RegisterPage />
      </PublicOnly>
    ),
  },
  // Token-authorized; reachable signed-out (the token alone authorizes the change).
  { path: "/settings/confirm-email", element: <ConfirmEmailPage /> },
  // Email link-based auth flows (spec 104). The token-authorized callbacks are
  // reachable even while signed in (a user may click a link in another tab), so
  // they are NOT wrapped in PublicOnly; only the pure request pages are.
  { path: "/verify-email", element: <VerifyEmailPage /> },
  { path: "/verify-email/resend", element: <ResendVerificationPage /> },
  { path: "/magic-link", element: <MagicLinkPage /> },
  { path: "/reset-password", element: <ResetPasswordPage /> },
  {
    path: "/forgot-password",
    element: (
      <PublicOnly>
        <ForgotPasswordPage />
      </PublicOnly>
    ),
  },
  {
    element: <RequireAuth />,
    children: [
      { path: "/projects", element: <ProjectsPage /> },
      { path: "/projects/:projectId", element: <EditorPage /> },
      { path: "/settings", element: <SettingsPage /> },
      { path: "/invite/:token", element: <AcceptInvitePage /> },
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
