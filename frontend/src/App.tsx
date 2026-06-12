import { Navigate, RouterProvider, createBrowserRouter } from "react-router-dom";

import { PublicOnly, RequireAuth } from "@/auth/require-auth";
import { ProjectsPage } from "@/features/projects/projects-page";
import { EditorPage } from "@/pages/editor";
import { LoginPage } from "@/pages/login";
import { RegisterPage } from "@/pages/register";

const router = createBrowserRouter([
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
  {
    element: <RequireAuth />,
    children: [
      { path: "/", element: <Navigate to="/projects" replace /> },
      { path: "/projects", element: <ProjectsPage /> },
      { path: "/projects/:projectId", element: <EditorPage /> },
    ],
  },
  { path: "*", element: <Navigate to="/projects" replace /> },
]);

export function App() {
  return <RouterProvider router={router} />;
}
