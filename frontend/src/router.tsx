import { Navigate, type RouteObject, createBrowserRouter, createMemoryRouter } from "react-router-dom";

import { AppShell } from "@/components/app-shell";
import { RouteError } from "@/components/route-error";
import { Loading } from "@/components/states";
import { loadEditorRoute } from "@/lib/route-chunks";
import { RequireAuth } from "@/modules/auth";

// `handle.title` is the `common` key of the screen's document title; the landing has none and keeps
// the title of index.html.
const ROUTES: RouteObject[] = [
  // Public marketing landing page (reachable signed-out).
  { path: "/", lazy: () => import("@/routes/landing").then((m) => ({ Component: m.LandingRoute })) },
  // First-run admin creation; public (reachable signed-out, no setup gate itself).
  {
    path: "/setup",
    handle: { title: "title.setup" },
    lazy: () => import("@/routes/setup").then((m) => ({ Component: m.SetupRoute })),
  },
  {
    path: "/login",
    handle: { title: "title.login" },
    lazy: () => import("@/routes/login").then((m) => ({ Component: m.LoginRoute })),
  },
  {
    path: "/register",
    handle: { title: "title.register" },
    lazy: () => import("@/routes/register").then((m) => ({ Component: m.RegisterRoute })),
  },
  // Token-authorized; reachable signed-out (the token alone authorizes the change).
  {
    path: "/settings/confirm-email",
    handle: { title: "title.confirmEmail" },
    lazy: () => import("@/routes/confirm-email").then((m) => ({ Component: m.ConfirmEmailRoute })),
  },
  // Email link-based auth flows (spec 104). The token-authorized callbacks are
  // reachable even while signed in (a user may click a link in another tab), so
  // they are NOT wrapped in PublicOnly; only the pure request pages are.
  {
    path: "/verify-email",
    handle: { title: "title.verifyEmail" },
    lazy: () => import("@/routes/verify-email").then((m) => ({ Component: m.VerifyEmailRoute })),
  },
  {
    path: "/verify-email/resend",
    handle: { title: "title.resendVerification" },
    lazy: () =>
      import("@/routes/resend-verification").then((m) => ({ Component: m.ResendVerificationRoute })),
  },
  {
    path: "/magic-link",
    handle: { title: "title.magicLink" },
    lazy: () => import("@/routes/magic-link").then((m) => ({ Component: m.MagicLinkRoute })),
  },
  {
    path: "/reset-password",
    handle: { title: "title.resetPassword" },
    lazy: () => import("@/routes/reset-password").then((m) => ({ Component: m.ResetPasswordRoute })),
  },
  {
    path: "/forgot-password",
    handle: { title: "title.forgotPassword" },
    lazy: () => import("@/routes/forgot-password").then((m) => ({ Component: m.ForgotPasswordRoute })),
  },
  {
    element: <RequireAuth />,
    children: [
      {
        path: "/projects",
        handle: { title: "title.projects" },
        lazy: () => import("@/routes/projects").then((m) => ({ Component: m.ProjectsRoute })),
      },
      {
        path: "/projects/:projectId",
        handle: { title: "title.editor" },
        lazy: () => loadEditorRoute().then((m) => ({ Component: m.EditorRoute })),
      },
      {
        path: "/settings",
        handle: { title: "title.settings" },
        lazy: () => import("@/routes/settings").then((m) => ({ Component: m.SettingsRoute })),
      },
      {
        path: "/invite/:token",
        handle: { title: "title.invite" },
        lazy: () => import("@/routes/invite").then((m) => ({ Component: m.InviteRoute })),
      },
      {
        path: "/join/:token",
        handle: { title: "title.join" },
        lazy: () => import("@/routes/join").then((m) => ({ Component: m.JoinRoute })),
      },
    ],
  },
  { path: "*", element: <Navigate to="/projects" replace /> },
];

/**
 * Every route sits under one root, so a lazy load gets the app's own screen and every screen gets the
 * shell. The error boundary sits one level down: on the root it would replace the shell itself.
 */
const ROOT: RouteObject = {
  element: <AppShell />,
  HydrateFallback: Loading,
  children: [{ ErrorBoundary: RouteError, children: ROUTES }],
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
