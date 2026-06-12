import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError } from "@/lib/api-client";

import { confirmEmailChange } from "./api";

type State = { kind: "loading" } | { kind: "done"; email: string } | { kind: "error"; message: string };

export function ConfirmEmailPage() {
  const [params] = useSearchParams();
  const token = params.get("token");
  const [state, setState] = useState<State>({ kind: "loading" });
  const ran = useRef(false);

  useEffect(() => {
    if (ran.current) return; // single-use token: confirm exactly once
    ran.current = true;
    if (!token) {
      setState({ kind: "error", message: "This link is missing its confirmation token." });
      return;
    }
    void confirmEmailChange(token)
      .then((user) => setState({ kind: "done", email: user.email }))
      .catch((e) =>
        setState({
          kind: "error",
          message: e instanceof ApiError ? e.message : "Could not confirm the email change.",
        }),
      );
  }, [token]);

  return (
    <div className="mx-auto max-w-md p-6">
      <Card>
        <CardHeader>
          <CardTitle>Confirm email change</CardTitle>
          <CardDescription>
            {state.kind === "loading" && "Confirming your new email…"}
            {state.kind === "done" && `Your email is now ${state.email}.`}
            {state.kind === "error" && state.message}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button asChild>
            <Link to="/settings">Go to settings</Link>
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
