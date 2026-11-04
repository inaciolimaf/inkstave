import { config } from "@/config";

/** The Git Smart HTTP address of a project (spec 121). The password is a Git access token. */
export function gitCloneUrl(projectId: string): string {
  const origin = config.apiBaseUrl || window.location.origin;
  return `${origin}/api/v1/git/projects/${projectId}.git`;
}
