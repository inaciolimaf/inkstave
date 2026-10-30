import { PublicOnly, RegisterPage } from "@/modules/auth";

export function RegisterRoute() {
  return (
    <PublicOnly>
      <RegisterPage />
    </PublicOnly>
  );
}
