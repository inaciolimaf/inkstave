/** Accept-invite screen at `/invite/:token` (spec 33). */
import { useMutation, useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError } from "@/lib/api-client";

import { acceptInvite, declineInvite, getInvitePreview } from "./api";

export function AcceptInvitePage() {
  const { t } = useTranslation("sharing");
  const { token = "" } = useParams<{ token: string }>();
  const navigate = useNavigate();

  const preview = useQuery({
    queryKey: ["invite-preview", token],
    queryFn: () => getInvitePreview(token),
    retry: false,
  });

  const accept = useMutation({
    mutationFn: () => acceptInvite(token),
    onSuccess: (result) => {
      toast.success(t("accept.joined"));
      navigate(`/projects/${result.projectId}`);
    },
    onError: (e) =>
      toast.error(e instanceof ApiError && e.message ? e.message : t("accept.acceptError")),
  });

  const decline = useMutation({
    mutationFn: () => declineInvite(token),
    onSuccess: () => navigate("/projects"),
    onError: (e) =>
      toast.error(e instanceof ApiError && e.message ? e.message : t("accept.declineError")),
  });

  const gone = preview.error instanceof ApiError && preview.error.status === 410;

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <Card className="w-full max-w-md">
        {preview.isLoading && (
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            {t("accept.loading")}
          </CardContent>
        )}

        {gone && (
          <>
            <CardHeader>
              <CardTitle>{t("accept.unavailableTitle")}</CardTitle>
              <CardDescription>{t("accept.unavailableDescription")}</CardDescription>
            </CardHeader>
            <CardContent>
              <Button variant="outline" onClick={() => navigate("/projects")}>
                {t("accept.backToProjects")}
              </Button>
            </CardContent>
          </>
        )}

        {preview.isError && !gone && (
          <CardContent className="py-10 text-center text-sm text-destructive" role="alert">
            {t("accept.notFound")}
          </CardContent>
        )}

        {preview.data && (
          <>
            <CardHeader>
              <CardTitle>
                {t("accept.invitedTo", { projectName: preview.data.projectName })}
              </CardTitle>
              <CardDescription>
                {t("accept.invitedBy", { inviterName: preview.data.inviterName })}
                <strong>{t(`role.${preview.data.role}`)}</strong>.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex gap-2">
              <Button onClick={() => accept.mutate()} disabled={accept.isPending}>
                {t("accept.accept")}
              </Button>
              <Button
                variant="outline"
                onClick={() => decline.mutate()}
                disabled={decline.isPending}
              >
                {t("accept.decline")}
              </Button>
            </CardContent>
          </>
        )}
      </Card>
    </div>
  );
}
