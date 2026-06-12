import { Clock, FileCheck2, FileText, Sparkles, Users } from "lucide-react";
import type { CSSProperties, ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";

import { useReveal } from "./use-reveal";

export function FeatureGrid() {
  const { t } = useTranslation("landing");
  const head = useReveal<HTMLDivElement>();

  return (
    <section id="features" className="relative scroll-mt-24 py-24 sm:py-32">
      <div className="mx-auto max-w-6xl px-5 sm:px-8">
        <div ref={head} className="reveal max-w-2xl">
          <SectionEyebrow>{t("features.eyebrow")}</SectionEyebrow>
          <h2 className="mt-4 font-display text-3xl font-normal leading-tight tracking-tight text-ink sm:text-[2.6rem]">
            {t("features.title")}
          </h2>
          <p className="mt-4 text-base leading-relaxed text-ink-soft">{t("features.subhead")}</p>
        </div>

        <div className="mt-14 grid gap-4 md:grid-cols-3">
          <FeatureCard
            className="md:col-span-2"
            icon={<Users className="size-4" />}
            title={t("features.collabTitle")}
            body={t("features.collabBody")}
            delay={0}
            visual={<CollabVisual />}
          />
          <FeatureCard
            icon={<Sparkles className="size-4" />}
            title={t("features.agentTitle")}
            body={t("features.agentBody")}
            delay={80}
            visual={<AgentVisual />}
          />
          <FeatureCard
            icon={<FileCheck2 className="size-4" />}
            title={t("features.compileTitle")}
            body={t("features.compileBody")}
            delay={0}
            visual={<CompileVisual />}
          />
          <FeatureCard
            icon={<FileText className="size-4" />}
            title={t("features.previewTitle")}
            body={t("features.previewBody")}
            delay={80}
            visual={<PreviewVisual />}
          />
          <FeatureCard
            icon={<Clock className="size-4" />}
            title={t("features.historyTitle")}
            body={t("features.historyBody")}
            delay={160}
            visual={<HistoryVisual />}
          />
        </div>
      </div>
    </section>
  );
}

function FeatureCard({
  icon,
  title,
  body,
  visual,
  className,
  delay = 0,
}: {
  icon: ReactNode;
  title: string;
  body: string;
  visual: ReactNode;
  className?: string;
  delay?: number;
}) {
  const ref = useReveal<HTMLDivElement>();
  return (
    <article
      ref={ref}
      style={{ "--reveal-delay": `${delay}ms` } as CSSProperties}
      className={cn(
        "reveal group flex flex-col overflow-hidden rounded-2xl border border-rule bg-[hsl(36_36%_99%)] p-6 transition-all duration-300 hover:-translate-y-1 hover:border-ink/20 hover:shadow-[0_30px_60px_-40px_hsl(var(--ink)/0.5)]",
        className,
      )}
    >
      <div className="flex items-center gap-2.5 text-ink">
        <span className="inline-flex size-8 items-center justify-center rounded-lg border border-rule bg-paper-deep/50">
          {icon}
        </span>
        <h3 className="font-display text-xl font-medium tracking-tight">{title}</h3>
      </div>
      <p className="mt-3 max-w-md text-sm leading-relaxed text-ink-soft">{body}</p>
      <div className="mt-6 flex-1">{visual}</div>
    </article>
  );
}

/* ---------------------------------------------------------------- */
/* Tiny recreated mockups — pure CSS, no screenshots.               */
/* ---------------------------------------------------------------- */

function VisualFrame({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={cn(
        "flex h-full flex-col overflow-hidden rounded-xl border border-rule bg-paper/70",
        className,
      )}
    >
      {children}
    </div>
  );
}

function CollabVisual() {
  return (
    <VisualFrame className="relative min-h-[170px] justify-center p-6 font-mono text-[0.72rem] leading-[2] text-ink-soft">
      <div>
        <span className="text-indigo-700">\section</span>
        <span className="text-ink-faint">{"{"}</span>Results
        <span className="text-ink-faint">{"}"}</span>
      </div>
      <div className="relative">
        The estimator converges&nbsp;
        {/* Cursor 1 */}
        <span className="relative inline-block align-baseline">
          <span className="inline-block h-[1.15em] w-px translate-y-[3px] bg-rose-500" />
          <span className="cursor-bob absolute -top-5 left-0 whitespace-nowrap rounded bg-rose-500 px-1.5 py-0.5 text-[0.6rem] font-medium text-white">
            Mara
          </span>
        </span>
      </div>
      <div className="relative">
        quickly under mild assumptions&nbsp;
        {/* Cursor 2 */}
        <span className="relative inline-block align-baseline">
          <span className="inline-block h-[1.15em] w-px translate-y-[3px] bg-sky-600" />
          <span
            className="cursor-bob absolute -top-5 left-0 whitespace-nowrap rounded bg-sky-600 px-1.5 py-0.5 text-[0.6rem] font-medium text-white"
            style={{ animationDelay: "0.9s" }}
          >
            Theo
          </span>
        </span>
      </div>
      <div className="text-ink-faint">on the held-out set.</div>
    </VisualFrame>
  );
}

function AgentVisual() {
  const { t } = useTranslation("landing");
  return (
    <VisualFrame className="items-center justify-center p-5">
      <div className="w-full max-w-[15rem] space-y-1.5 rounded-lg border border-rule bg-[hsl(36_30%_99%)] p-3 font-mono text-[0.62rem]">
        <div className="text-rose-700/90">
          <span className="mr-1 text-rose-400">−</span>in great detail
        </div>
        <div className="text-emerald-700">
          <span className="mr-1 text-emerald-500">+</span>concisely
        </div>
        <div className="flex gap-1.5 pt-1.5">
          <span className="rounded bg-ink px-1.5 py-0.5 text-[0.58rem] text-paper">
            {t("demo.accept")}
          </span>
          <span className="rounded border border-rule px-1.5 py-0.5 text-[0.58rem] text-ink-soft">
            {t("demo.reject")}
          </span>
        </div>
      </div>
    </VisualFrame>
  );
}

function CompileVisual() {
  const { t } = useTranslation("landing");
  return (
    <VisualFrame className="items-center justify-center p-5">
      <div className="flex flex-col items-center gap-2.5">
        <span className="inline-flex items-center gap-1.5 rounded-md bg-ink px-3 py-1.5 text-[0.7rem] font-medium text-paper">
          <FileCheck2 className="size-3.5" /> {t("features.compileButton")}
        </span>
        <div className="h-1 w-24 overflow-hidden rounded-full bg-rule">
          <div className="h-full w-2/3 rounded-full bg-emerald-500" />
        </div>
        <span className="text-[0.62rem] text-ink-faint">{t("features.compileStatus")}</span>
      </div>
    </VisualFrame>
  );
}

function PreviewVisual() {
  return (
    <VisualFrame className="items-center justify-center p-5">
      <div className="w-20 rounded-sm border border-rule bg-white p-2 shadow-sm">
        <div className="mx-auto mb-2 h-1.5 w-3/4 rounded bg-ink/70" />
        <div className="space-y-1">
          {[100, 92, 96, 70, 88, 60].map((w, i) => (
            <div key={i} className="h-0.5 rounded bg-rule" style={{ width: `${w}%` }} />
          ))}
        </div>
      </div>
    </VisualFrame>
  );
}

function HistoryVisual() {
  const { t } = useTranslation("landing");
  const items = [
    t("features.historyItem1"),
    t("features.historyItem2"),
    t("features.historyItem3"),
  ];
  return (
    <VisualFrame className="justify-center p-6">
      <ol className="relative ml-1 space-y-3 border-l border-rule pl-4 text-[0.66rem] text-ink-soft">
        {items.map((label, i) => (
          <li key={label} className="relative">
            <span
              className={cn(
                "absolute -left-[1.42rem] top-0.5 size-2 rounded-full border-2 border-paper",
                i === 0 ? "bg-ink" : "bg-rule",
              )}
            />
            {label}
          </li>
        ))}
      </ol>
    </VisualFrame>
  );
}

export function SectionEyebrow({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-2.5 text-[0.72rem] font-medium uppercase tracking-[0.2em] text-ink-faint">
      <span className="h-px w-6 bg-ink-faint/50" />
      {children}
    </span>
  );
}
