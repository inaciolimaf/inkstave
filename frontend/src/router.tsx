import { Navigate, type RouteObject, createBrowserRouter, createMemoryRouter } from "react-router-dom";

import { RouteError } from "@/components/route-error";
import { Loading } from "@/components/states";
import { RequireAuth } from "@/modules/auth";

const ROUTES: RouteObject[] = [
  // Public marketing landing page (reachable signed-out).
  { path: "/", lazy: () => import("@/routes/landing").then((m) => ({ Component: m.LandingRoute })) },
  // First-run admin creation; public (reachable signed-out, no setup gate itself).
  { path: "/setup", lazy: () => import("@/routes/setup").then((m) => ({ Component: m.SetupRoute })) },
  { path: "/login", lazy: () => import("@/routes/login").then((m) => ({ Component: m.LoginRoute })) },
  {
    path: "/register",
    lazy: () => import("@/routes/register").then((m) => ({ Component: m.RegisterRoute })),
  },
  // Token-authorized; reachable signed-out (the token alone authorizes the change).
  {
    path: "/settings/confirm-email",
    lazy: () => import("@/routes/confirm-email").then((m) => ({ Component: m.ConfirmEmailRoute })),
  },
  // Email link-based auth flows (spec 104). The token-authorized callbacks are
  // reachable even while signed in (a user may click a link in another tab), so
  // they are NOT wrapped in PublicOnly; only the pure request pages are.
  {
    path: "/verify-email",
    lazy: () => import("@/routes/verify-email").then((m) => ({ Component: m.VerifyEmailRoute })),
  },
  {
    path: "/verify-email/resend",
    lazy: () =>
      import("@/routes/resend-verification").then((m) => ({ Component: m.ResendVerificationRoute })),
  },
  {
    path: "/magic-link",
    lazy: () => import("@/routes/magic-link").then((m) => ({ Component: m.MagicLinkRoute })),
  },
  {
    path: "/reset-password",
    lazy: () => import("@/routes/reset-password").then((m) => ({ Component: m.ResetPasswordRoute })),
  },
  {
    path: "/forgot-password",
    lazy: () => import("@/routes/forgot-password").then((m) => ({ Component: m.ForgotPasswordRoute })),
  },
  {
    element: <RequireAuth />,
    children: [
      {
        path: "/projects",
        lazy: () => import("@/routes/projects").then((m) => ({ Component: m.ProjectsRoute })),
      },
      {
        path: "/projects/:projectId",
        lazy: () => import("@/routes/editor").then((m) => ({ Component: m.EditorRoute })),
      },
      {
        path: "/settings",
        lazy: () => import("@/routes/settings").then((m) => ({ Component: m.SettingsRoute })),
      },
      {
        path: "/invite/:token",
        lazy: () => import("@/routes/invite").then((m) => ({ Component: m.InviteRoute })),
      },
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
