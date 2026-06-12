import { Navigate, RouterProvider, createBrowserRouter } from "react-router-dom";

import { PublicOnly, RequireAuth } from "@/auth/require-auth";
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
  return <RouterProvider router={router} />;
}
