import { Navigate, RouterProvider, createBrowserRouter } from "react-router-dom";

import { PublicOnly, RequireAuth } from "@/auth/require-auth";
import { ForgotPasswordPage } from "@/features/auth/ForgotPasswordPage";
import { useApplyTheme } from "@/features/editor/use-apply-theme";
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

const router = createBrowserRouter([
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
]);

export function App() {
  useApplyTheme(); // keep <html> in sync with the user's theme preference (spec 59)
  return <RouterProvider router={router} />;
}
