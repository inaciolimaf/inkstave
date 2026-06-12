/**
 * Compile-problems API client + types (spec 27).
 *
 * Layout note: spec 27 §5.3 nominally placed this client under
 * `src/lib/api/problems.ts`. It is intentionally co-located here with the
 * `pdf-preview` feature it serves (cohesion over the literal layout), which is
 * the only consumer. `src/lib/api/problems.ts` does not exist by design.
 */
import { ApiError, apiClient } from "@/lib/api-client";

export type ProblemSeverity = "error" | "warning" | "info";

export interface Problem {
  severity: ProblemSeverity;
  message: string;
  file: string | null;
  line: number | null;
  end_line: number | null;
  raw: string;
  rule: string;
}

export interface CompileProblems {
  compile_id: string;
  errors: number;
  warnings: number;
  infos: number;
  problems: Problem[];
}

export type ProblemsReason = "log_unavailable" | "error";

export type ProblemsResult =
  | { ok: true; value: CompileProblems }
  | { ok: false; reason: ProblemsReason };

/** Fetch parsed problems for a compile id (or the literal `"latest"`). */
export async function getProblems(projectId: string, compileId: string): Promise<ProblemsResult> {
  try {
    const value = await apiClient.get<CompileProblems>(
      `/api/v1/projects/${projectId}/compiles/${compileId}/problems`,
    );
    return { ok: true, value };
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      return { ok: false, reason: "log_unavailable" };
    }
    return { ok: false, reason: "error" };
  }
}
