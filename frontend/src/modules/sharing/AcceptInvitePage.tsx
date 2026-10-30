/** Accept-invite screen at `/invite/:token` (spec 33). */
import { useMutation, useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { AuthShell } from "@/modules/auth";
import { ApiError } from "@/lib/api-client";

import { acceptInvite, declineInvite, getInvitePreview } from "./api";

export function AcceptInvitePage() {
  const { t } = useTranslation(["sharing", "common"]);
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
    onError: (e) => toast.error(e instanceof ApiError && e.message ? e.message : t("accept.acceptError")),
  });

  const decline = useMutation({
    mutationFn: () => declineInvite(token),
    onSuccess: () => navigate("/projects"),
    onError: (e) => toast.error(e instanceof ApiError && e.message ? e.message : t("accept.declineError")),
  });

  const gone = preview.error instanceof ApiError && preview.error.status === 410;

  if (preview.data) {
    return (
      <AuthShell
        title={t("accept.invitedTo", { projectName: preview.data.projectName })}
        description={
          <>
            {t("accept.invitedBy", { inviterName: preview.data.inviterName })}
            <strong>{t(`role.${preview.data.role}`)}</strong>.
          </>
        }
      >
        <div className="flex gap-2">
          <Button onClick={() => accept.mutate()} disabled={accept.isPending}>
            {t("accept.accept")}
          </Button>
          <Button variant="outline" onClick={() => decline.mutate()} disabled={decline.isPending}>
            {t("accept.decline")}
          </Button>
        </div>
      </AuthShell>
    );
  }

  if (gone) {
    return (
      <AuthShell title={t("accept.unavailableTitle")} description={t("accept.unavailableDescription")}>
        <Button onClick={() => navigate("/projects")}>{t("accept.backToProjects")}</Button>
      </AuthShell>
    );
  }

  return (
    <AuthShell title={t("common:title.invite")}>
      {preview.isError ? (
        <p className="text-body text-error-text" role="alert">
          {t("accept.notFound")}
        </p>
      ) : (
        <p className="text-body text-muted-foreground">{t("accept.loading")}</p>
      )}
    </AuthShell>
  );
}
