/** First-run setup API (spec 63 → spec-57 `/api/setup` endpoints). */
import { apiClient } from "@/lib/api-client";

export interface SetupStatus {
  needsSetup: boolean;
}

/** Whether a first admin still needs to be created. */
export async function getSetupStatus(): Promise<SetupStatus> {
  const wire = await apiClient.get<{ needs_setup: boolean }>("/api/setup/status");
  return { needsSetup: wire.needs_setup };
}

export interface CreateAdminInput {
  email: string;
  password: string;
  displayName: string;
}

/** Create the first admin account (locked once one exists → 409). */
export async function createFirstAdmin(input: CreateAdminInput): Promise<void> {
  await apiClient.post(
    "/api/setup/admin",
    { email: input.email, password: input.password, display_name: input.displayName },
    { auth: false },
  );
}
