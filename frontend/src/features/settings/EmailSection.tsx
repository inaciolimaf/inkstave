import { useState } from "react";
import { toast } from "sonner";

import { useAuth } from "@/auth/auth-context";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import { changeEmail } from "./api";
import { errMessage } from "./errMessage";

export function EmailSection() {
  const { user, refreshUser } = useAuth();
  const [newEmail, setNewEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [sentTo, setSentTo] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await changeEmail({ new_email: newEmail.trim(), current_password: password });
      setSentTo(newEmail.trim());
      setNewEmail("");
      setPassword("");
      await refreshUser();
      toast.success("Confirmation sent.");
    } catch (err) {
      toast.error(errMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Email</CardTitle>
        <CardDescription>
          Current: <span className="font-medium">{user?.email}</span>
          {user?.pending_email && (
            <span className="ml-1 text-amber-600">· pending: {user.pending_email}</span>
          )}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {sentTo ? (
          <p role="status" className="text-sm text-muted-foreground">
            We sent a confirmation link to <span className="font-medium">{sentTo}</span>. The change
            takes effect once you confirm it.
          </p>
        ) : (
          <form onSubmit={submit} className="space-y-4">
            <div className="space-y-1">
              <Label htmlFor="new-email">New email</Label>
              <Input
                id="new-email"
                type="email"
                value={newEmail}
                onChange={(e) => setNewEmail(e.target.value)}
                required
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="email-pw">Password</Label>
              <Input
                id="email-pw"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            <Button type="submit" disabled={busy || !newEmail.trim() || !password}>
              {busy ? "Sending…" : "Change email"}
            </Button>
          </form>
        )}
      </CardContent>
    </Card>
  );
}
