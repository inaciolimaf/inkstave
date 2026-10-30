/**
 * Every route of the app, with a URL to open it by. `tests/e2e-routes.test.ts` fails when this list
 * falls behind the router. The ids are fake: a screen must survive one it cannot find.
 */
export const FAKE_ID = "00000000-0000-4000-8000-000000000000";

export const ROUTES: ReadonlyArray<{ path: string; url: string }> = [
  { path: "/", url: "/" },
  { path: "/setup", url: "/setup" },
  { path: "/login", url: "/login" },
  { path: "/register", url: "/register" },
  { path: "/settings/confirm-email", url: "/settings/confirm-email?token=fake" },
  { path: "/verify-email", url: "/verify-email?token=fake" },
  { path: "/verify-email/resend", url: "/verify-email/resend" },
  { path: "/magic-link", url: "/magic-link?token=fake" },
  { path: "/reset-password", url: "/reset-password?token=fake" },
  { path: "/forgot-password", url: "/forgot-password" },
  { path: "/projects", url: "/projects" },
  { path: "/projects/:projectId", url: `/projects/${FAKE_ID}` },
  { path: "/settings", url: "/settings" },
  { path: "/invite/:token", url: "/invite/fake" },
  { path: "*", url: "/no-such-page" },
];
