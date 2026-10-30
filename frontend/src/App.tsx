import { RouterProvider } from "react-router-dom";

import { useApplyTheme } from "@/features/editor/use-apply-theme";
import { createAppRouter } from "@/router";

const router = createAppRouter();

export function App() {
  useApplyTheme(); // keep <html> in sync with the user's theme preference (spec 59)
  return <RouterProvider router={router} />;
}
