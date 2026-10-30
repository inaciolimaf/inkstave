import { LoginPage, PublicOnly } from "@/modules/auth";

export function LoginRoute() {
  return (
    <PublicOnly>
      <LoginPage />
    </PublicOnly>
  );
}
