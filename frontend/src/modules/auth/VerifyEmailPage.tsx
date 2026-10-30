import { Loader2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api-client";

import { AuthShell } from "./AuthShell";
import { confirmVerification } from "./api";

type State = { kind: "loading" } | { kind: "success" } | { kind: "expired" } | { kind: "invalid" };

export function VerifyEmailPage() {
  const { t } = useTranslation("auth");
  const [params] = useSearchParams();
  const token = params.get("token");
  const [state, setState] = useState<State>({ kind: "loading" });
  const ran = useRef(false);

  useEffect(() => {
    if (ran.current) return; // single-use token: confirm exactly once
    ran.current = true;
    if (!token) {
      setState({ kind: "invalid" });
      return;
    }
    void confirmVerification(token)
      .then(() => setState({ kind: "success" }))
      .catch((e) => {
        const expired = e instanceof ApiError && e.status === 410;
        setState({ kind: expired ? "expired" : "invalid" });
      });
  }, [token]);

  if (state.kind === "loading") {
    return (
      <AuthShell title={t("verifyEmail.title")}>
        <p className="flex items-center gap-2 text-sm text-muted-foreground" role="status">
          <Loader2 className="size-4 animate-spin" />
          {t("verifyEmail.verifying")}
        </p>
      </AuthShell>
    );
  }

  if (state.kind === "success") {
    return (
      <AuthShell title={t("verifyEmail.title")}>
        <Alert role="alert">
          <AlertDescription>{t("verifyEmail.success")}</AlertDescription>
        </Alert>
        <div className="mt-4 flex flex-col gap-2">
          <Button asChild className="w-full">
            <Link to="/projects">{t("verifyEmail.goToProjects")}</Link>
          </Button>
          <Button asChild variant="outline" className="w-full">
            <Link to="/login">{t("verifyEmail.goToLogin")}</Link>
          </Button>
        </div>
      </AuthShell>
    );
  }

  // expired or invalid
  return (
    <AuthShell title={t("verifyEmail.title")}>
      <Alert variant="destructive" role="alert">
        <AlertDescription>
          {state.kind === "expired" ? t("verifyEmail.expired") : t("verifyEmail.invalid")}
        </AlertDescription>
      </Alert>
      <Button asChild className="mt-4 w-full">
        <Link to="/verify-email/resend">{t("verifyEmail.requestNew")}</Link>
      </Button>
    </AuthShell>
  );
}
