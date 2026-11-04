/** Share-link screen at `/join/:token` (spec 116): a preview, then Join, or Open when access is already there. */
import { useMutation, useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";

import { QueryView } from "@/components/states";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api-client";
import { AuthShell } from "@/modules/auth";

import { getSharePreview, joinShareLink } from "./api";
import { alreadyHasAccess } from "./access";
import type { SharePreview } from "./types";

function JoinActions({ token, preview }: { token: string; preview: SharePreview }) {
  const { t } = useTranslation("sharing");
  const navigate = useNavigate();

  const join = useMutation({
    mutationFn: () => joinShareLink(token),
    onSuccess: (result) => {
      toast.success(t("join.joined"));
      navigate(`/projects/${result.projectId}`);
    },
    onError: (e) => toast.error(e instanceof ApiError && e.message ? e.message : t("join.joinError")),
  });

  if (alreadyHasAccess(preview.alreadyMemberRole, preview.role)) {
    return <Button onClick={() => navigate(`/projects/${preview.projectId}`)}>{t("join.open")}</Button>;
  }
  return (
    <Button onClick={() => join.mutate()} disabled={join.isPending}>
      {t("join.join")}
    </Button>
  );
}

function LinkUnavailable() {
  const { t } = useTranslation(["sharing", "common"]);
  const navigate = useNavigate();
  return (
    <AuthShell title={t("join.unavailableTitle")} description={t("join.unavailable")}>
      <Button onClick={() => navigate("/projects")}>{t("join.backToProjects")}</Button>
    </AuthShell>
  );
}

export function JoinLinkPage() {
  const { t } = useTranslation(["sharing", "common"]);
  const { token = "" } = useParams<{ token: string }>();

  const preview = useQuery({
    queryKey: ["share-link-preview", token],
    queryFn: () => getSharePreview(token),
    retry: false,
  });

  if (preview.error instanceof ApiError && preview.error.status === 404) return <LinkUnavailable />;

  const data = preview.data;
  const has = data ? alreadyHasAccess(data.alreadyMemberRole, data.role) : false;
  const title = !data ? t("common:title.join") : has ? t("join.alreadyTitle") : data.projectName;
  const description = !data
    ? undefined
    : has
      ? data.projectName
      : t("join.description", { ownerName: data.ownerName, role: t(`role.${data.role}`) });

  return (
    <AuthShell title={title} description={description}>
      <QueryView
        query={preview}
        loading={<p className="text-body text-muted-foreground">{t("join.loading")}</p>}
        errorMessage={t("join.loadError")}
        errorClassName="flex-col items-start gap-3"
      >
        {(loaded) => <JoinActions token={token} preview={loaded} />}
      </QueryView>
    </AuthShell>
  );
}
