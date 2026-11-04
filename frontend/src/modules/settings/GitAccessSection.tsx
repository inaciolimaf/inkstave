import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { formatDate } from "@/lib/formatting";

import { createGitToken, type GitToken, listGitTokens, revokeGitToken } from "./git-api";
import { errMessage } from "./errMessage";
import { SettingsSection } from "./SettingsSection";

const TOKENS_KEY = ["git-tokens"] as const;

function TokenRow({ token, onRevoked }: { token: GitToken; onRevoked: () => void }) {
  const { t } = useTranslation("settings");
  const revoke = useMutation({
    mutationFn: () => revokeGitToken(token.id),
    onSuccess: () => {
      toast.success(t("git.revoked"));
      onRevoked();
    },
    onError: (err) => toast.error(errMessage(err)),
  });
  return (
    <li className="flex flex-wrap items-center justify-between gap-2 border-b py-3">
      <div className="min-w-0">
        <p className="font-medium">{token.name}</p>
        <p className="font-mono text-small text-muted-foreground">
          {t("git.prefix", { prefix: token.prefix })}
        </p>
        <p className="text-small text-muted-foreground">
          {t("git.createdOn", { date: formatDate(token.created_at) })} ·{" "}
          {token.last_used_at
            ? t("git.lastUsed", { date: formatDate(token.last_used_at) })
            : t("git.neverUsed")}
          {token.expires_at ? ` · ${t("git.expires", { date: formatDate(token.expires_at) })}` : ""}
        </p>
      </div>
      <AlertDialog>
        <AlertDialogTrigger asChild>
          <Button variant="ghost" size="sm">
            {t("git.revoke")}
          </Button>
        </AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("git.revokeTitle")}</AlertDialogTitle>
            <AlertDialogDescription>{t("git.revokeBody")}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("git.cancel")}</AlertDialogCancel>
            <AlertDialogAction onClick={() => revoke.mutate()}>{t("git.revokeConfirm")}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </li>
  );
}

function ShownOnce({ token }: { token: string }) {
  const { t } = useTranslation("settings");
  return (
    <div role="status" className="mb-6 space-y-2 rounded border border-border p-3">
      <p className="text-body">{t("git.created")}</p>
      <div className="flex items-center gap-2">
        <code className="min-w-0 flex-1 break-all font-mono text-small">{token}</code>
        <Button
          size="sm"
          variant="outline"
          onClick={() => {
            void navigator.clipboard?.writeText(token);
            toast.success(t("git.copied"));
          }}
        >
          {t("git.copy")}
        </Button>
      </div>
    </div>
  );
}

function CreateForm({ onCreated }: { onCreated: (token: string) => void }) {
  const { t } = useTranslation("settings");
  const [name, setName] = useState("");
  const [expires, setExpires] = useState("");
  const create = useMutation({
    mutationFn: () =>
      createGitToken({
        name: name.trim(),
        expires_at: expires ? new Date(`${expires}T23:59:59`).toISOString() : null,
      }),
    onSuccess: (issued) => {
      setName("");
      setExpires("");
      onCreated(issued.token);
    },
    onError: (err) => toast.error(errMessage(err)),
  });
  return (
    <form
      className="max-w-md space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (name.trim()) create.mutate();
      }}
    >
      <div className="space-y-1">
        <Label htmlFor="git-token-name">{t("git.name")}</Label>
        <Input
          id="git-token-name"
          value={name}
          maxLength={100}
          placeholder={t("git.namePlaceholder")}
          onChange={(e) => setName(e.target.value)}
          required
        />
      </div>
      <div className="space-y-1">
        <Label htmlFor="git-token-expires">{t("git.expiry")}</Label>
        <Input
          id="git-token-expires"
          type="date"
          value={expires}
          min={new Date().toISOString().slice(0, 10)}
          onChange={(e) => setExpires(e.target.value)}
        />
      </div>
      <Button type="submit" variant="outline" disabled={create.isPending || !name.trim()}>
        {create.isPending ? t("git.creating") : t("git.create")}
      </Button>
    </form>
  );
}

/** Settings → "Git access tokens" (spec 121): create (shown once), list and revoke. */
export function GitAccessSection() {
  const { t } = useTranslation("settings");
  const qc = useQueryClient();
  const [shown, setShown] = useState<string | null>(null);
  const { data, isPending, isError } = useQuery({ queryKey: TOKENS_KEY, queryFn: listGitTokens });
  const refresh = () => void qc.invalidateQueries({ queryKey: TOKENS_KEY });

  return (
    <SettingsSection title={t("git.title")} description={t("git.description")}>
      {shown && <ShownOnce token={shown} />}
      <CreateForm
        onCreated={(token) => {
          setShown(token);
          refresh();
        }}
      />
      <div className="mt-8">
        {isPending && <p className="text-body text-muted-foreground">{t("git.loading")}</p>}
        {isError && <p className="text-body text-error-text">{t("error.generic")}</p>}
        {data && data.tokens.length === 0 && (
          <p className="text-body text-muted-foreground">{t("git.empty")}</p>
        )}
        {data && data.tokens.length > 0 && (
          <ul>
            {data.tokens.map((token) => (
              <TokenRow key={token.id} token={token} onRevoked={refresh} />
            ))}
          </ul>
        )}
      </div>
    </SettingsSection>
  );
}
