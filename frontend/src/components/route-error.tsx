/** The router's error screen: a screen that crashed while rendering lands here. */
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate, useRouteError } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError } from "@/lib/api-client";

export function RouteError() {
  const { t } = useTranslation("common");
  const error = useRouteError();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();

  // The crashed screen's queries are inactive once it unmounts: re-rendering the same bad response
  // would crash again. Navigating to the same URL makes the router drop the caught error.
  const retry = async () => {
    await queryClient.resetQueries({ type: "inactive" });
    navigate(location, { replace: true });
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-muted/30 p-4">
      <Card className="w-full max-w-sm" role="alert">
        <CardHeader>
          <CardTitle className="text-xl">{t("errorBoundary.title")}</CardTitle>
          <CardDescription>
            {error instanceof ApiError ? error.detail : t("errorBoundary.body")}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex gap-2">
          <Button onClick={() => void retry()}>{t("errorBoundary.retry")}</Button>
        </CardContent>
      </Card>
    </div>
  );
}
