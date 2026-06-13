import { Loader2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { useAuth } from "@/auth/auth-context";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api-client";

import { AuthShell } from "./AuthShell";
import { EmailRequestForm } from "./EmailRequestForm";
import { completeMagicLink, requestMagicLink } from "./api";

type CallbackState = { kind: "loading" } | { kind: "expired" } | { kind: "invalid" };

/** Callback branch: a `?token` is present, so sign the user in and redirect. */
function MagicLinkCallback({ token }: { token: string }) {
  const { t } = useTranslation("auth");
  const { loginWithTokenPair } = useAuth();
  const navigate = useNavigate();
  const [state, setState] = useState<CallbackState>({ kind: "loading" });
  const ran = useRef(false);

  useEffect(() => {
    if (ran.current) return; // single-use token: redeem exactly once
    ran.current = true;
    void completeMagicLink(token)
      .then(async (pair) => {
        await loginWithTokenPair(pair);
        navigate("/projects", { replace: true });
      })
      .catch((e) => {
        const expired = e instanceof ApiError && e.status === 410;
        setState({ kind: expired ? "expired" : "invalid" });
      });
  }, [token, loginWithTokenPair, navigate]);

  if (state.kind === "loading") {
    return (
      <AuthShell title={t("magicLink.requestTitle")}>
        <p className="flex items-center gap-2 text-sm text-muted-foreground" role="status">
          <Loader2 className="size-4 animate-spin" />
          {t("magicLink.verifying")}
        </p>
      </AuthShell>
    );
  }

  return (
    <AuthShell title={t("magicLink.requestTitle")}>
      <Alert variant="destructive" role="alert">
        <AlertDescription>
          {state.kind === "expired" ? t("magicLink.expired") : t("magicLink.invalid")}
        </AlertDescription>
      </Alert>
      <Button asChild className="mt-4 w-full">
        <Link to="/magic-link">{t("magicLink.requestNew")}</Link>
      </Button>
    </AuthShell>
  );
}

export function MagicLinkPage() {
  const { t } = useTranslation("auth");
  const [params] = useSearchParams();
  const token = params.get("token");

  if (token) return <MagicLinkCallback token={token} />;

  return (
    <AuthShell title={t("magicLink.requestTitle")} description={t("magicLink.requestDescription")}>
      <EmailRequestForm
        submitLabel={t("magicLink.submit")}
        successMessage={t("magicLink.requestSuccess")}
        request={requestMagicLink}
      />
      <p className="mt-4 text-center text-sm text-muted-foreground">
        <Link to="/login" className="font-medium text-primary underline-offset-4 hover:underline">
          {t("magicLink.backToLogin")}
        </Link>
      </p>
    </AuthShell>
  );
}
