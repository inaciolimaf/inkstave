/** Accept-invite screen at `/invite/:token` (spec 33). */
import { useMutation, useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";

import { QueryView } from "@/components/states";
import { Button } from "@/components/ui/button";
import { AuthShell } from "@/modules/auth";
import { ApiError } from "@/lib/api-client";

import { acceptInvite, declineInvite, getInvitePreview } from "./api";

function InviteActions({ token }: { token: string }) {
  const { t } = useTranslation(["sharing", "common"]);
  const navigate = useNavigate();

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

  return (
    <div className="flex gap-2">
      <Button onClick={() => accept.mutate()} disabled={accept.isPending}>
        {t("accept.accept")}
      </Button>
      <Button variant="outline" onClick={() => decline.mutate()} disabled={decline.isPending}>
        {t("accept.decline")}
      </Button>
    </div>
  );
}

function InviteUnavailable() {
  const { t } = useTranslation(["sharing", "common"]);
  const navigate = useNavigate();
  return (
    <AuthShell title={t("accept.unavailableTitle")} description={t("accept.unavailableDescription")}>
      <Button onClick={() => navigate("/projects")}>{t("accept.backToProjects")}</Button>
    </AuthShell>
  );
}

export function AcceptInvitePage() {
  const { t } = useTranslation(["sharing", "common"]);
  const { token = "" } = useParams<{ token: string }>();

  const preview = useQuery({
    queryKey: ["invite-preview", token],
    queryFn: () => getInvitePreview(token),
    retry: false,
  });

  if (preview.error instanceof ApiError && preview.error.status === 410) return <InviteUnavailable />;

  const invite = preview.isError ? undefined : preview.data;
  return (
    <AuthShell
      title={invite ? t("accept.invitedTo", { projectName: invite.projectName }) : t("common:title.invite")}
      description={
        invite && (
          <>
            {t("accept.invitedBy", { inviterName: invite.inviterName })}
            <strong>{t(`role.${invite.role}`)}</strong>.
          </>
        )
      }
    >
      <QueryView
        query={preview}
        loading={<p className="text-body text-muted-foreground">{t("accept.loading")}</p>}
        errorMessage={t("accept.notFound")}
        errorClassName="flex-col items-start gap-3"
      >
        {() => <InviteActions token={token} />}
      </QueryView>
    </AuthShell>
  );
}
