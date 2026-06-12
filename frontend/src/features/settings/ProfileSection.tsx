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

import { updateProfile } from "./api";
import { errMessage } from "./errMessage";

export function ProfileSection() {
  const { user, applyUser } = useAuth();
  const [name, setName] = useState(user?.display_name ?? "");
  const [busy, setBusy] = useState(false);
  const initials = (user?.display_name ?? "?").slice(0, 2).toUpperCase();

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const updated = await updateProfile({ display_name: name.trim() });
      applyUser(updated);
      toast.success("Profile updated.");
    } catch (err) {
      toast.error(errMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Profile</CardTitle>
        <CardDescription>Your display name and avatar.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={save} className="space-y-4">
          <div className="flex items-center gap-3">
            {user?.avatar_url ? (
              <img src={user.avatar_url} alt="" className="size-12 rounded-full object-cover" />
            ) : (
              <span
                aria-hidden
                className="flex size-12 items-center justify-center rounded-full bg-muted text-sm font-medium"
              >
                {initials}
              </span>
            )}
            <div className="flex-1 space-y-1">
              <Label htmlFor="display-name">Display name</Label>
              <Input
                id="display-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                maxLength={100}
                required
              />
            </div>
          </div>
          <Button type="submit" disabled={busy || !name.trim()}>
            {busy ? "Saving…" : "Save profile"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
