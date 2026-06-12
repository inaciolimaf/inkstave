/** Accept-invite screen at `/invite/:token` (spec 33). */
import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError } from "@/lib/api-client";

import { acceptInvite, declineInvite, getInvitePreview } from "./api";

export function AcceptInvitePage() {
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
      toast.success("You’ve joined the project.");
      navigate(`/projects/${result.projectId}`);
    },
    onError: (e) =>
      toast.error(e instanceof ApiError && e.message ? e.message : "Could not accept the invite."),
  });

  const decline = useMutation({
    mutationFn: () => declineInvite(token),
    onSuccess: () => navigate("/projects"),
    onError: (e) =>
      toast.error(e instanceof ApiError && e.message ? e.message : "Could not decline the invite."),
  });

  const gone = preview.error instanceof ApiError && preview.error.status === 410;

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <Card className="w-full max-w-md">
        {preview.isLoading && (
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            Loading invitation…
          </CardContent>
        )}

        {gone && (
          <>
            <CardHeader>
              <CardTitle>Invitation unavailable</CardTitle>
              <CardDescription>This invitation has expired or is no longer valid.</CardDescription>
            </CardHeader>
            <CardContent>
              <Button variant="outline" onClick={() => navigate("/projects")}>
                Back to projects
              </Button>
            </CardContent>
          </>
        )}

        {preview.isError && !gone && (
          <CardContent className="py-10 text-center text-sm text-destructive" role="alert">
            This invitation could not be found.
          </CardContent>
        )}

        {preview.data && (
          <>
            <CardHeader>
              <CardTitle>You’re invited to {preview.data.projectName}</CardTitle>
              <CardDescription>
                {preview.data.inviterName} invited you to join as{" "}
                <strong>{preview.data.role}</strong>.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex gap-2">
              <Button onClick={() => accept.mutate()} disabled={accept.isPending}>
                Accept
              </Button>
              <Button
                variant="outline"
                onClick={() => decline.mutate()}
                disabled={decline.isPending}
              >
                Decline
              </Button>
            </CardContent>
          </>
        )}
      </Card>
    </div>
  );
}
