/** Says what a run is doing and for how long, so a slow run does not look like a broken one. */
import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import type { AgentRunState } from "./types";

const SLOW_MS = 60_000;

const NAMED_TOOLS = new Set([
  "search_project",
  "read_file",
  "list_tree",
  "locate_section",
  "propose_edit",
  "view_image",
  "propose_create",
  "propose_delete",
  "propose_move",
]);

/** The key of the sentence for this moment of the run. */
export function runStatusKey(run: AgentRunState): string {
  if (run.phase === "stopping") return "run.stages.stopping";
  if (run.phase === "starting") return "run.stages.sending";
  const { stage, tool } = run.activity ?? {};
  if (!stage) return "run.stages.queued";
  return stage === "tool" && tool && NAMED_TOOLS.has(tool) ? `run.tools.${tool}` : `run.stages.${stage}`;
}

export function formatElapsed(ms: number): string {
  const seconds = Math.max(0, Math.floor(ms / 1000));
  if (seconds < 60) return `${seconds} s`;
  return `${Math.floor(seconds / 60)} min ${seconds % 60} s`;
}

export function RunStatus({ run }: { run: AgentRunState }) {
  const { t } = useTranslation("agent");
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  const started = run.startedAt ?? now;
  const quiet = now - (run.lastEventAt ?? started) >= SLOW_MS;
  return (
    <div className="min-w-0 text-small text-muted-foreground">
      <div className="flex items-center gap-2">
        <Loader2 aria-hidden="true" className="size-3.5 shrink-0 animate-spin" />
        <span role="status" className="truncate">
          {t(runStatusKey(run))}
        </span>
        <span aria-hidden="true" className="shrink-0 tabular-nums">
          {formatElapsed(now - started)}
        </span>
      </div>
      {quiet && <p role="status">{t("run.slow")}</p>}
    </div>
  );
}
