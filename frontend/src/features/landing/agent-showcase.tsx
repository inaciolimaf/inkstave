import { Check, FileSearch, GitPullRequestArrow, ShieldCheck, X } from "lucide-react";
import type { CSSProperties, ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { SectionEyebrow } from "./feature-grid";
import { useReveal } from "./use-reveal";

export function AgentShowcase() {
  const { t } = useTranslation("landing");
  const left = useReveal<HTMLDivElement>();
  const right = useReveal<HTMLDivElement>();

  const steps = [
    {
      icon: <FileSearch className="size-4" />,
      title: t("showcase.step1Title"),
      body: t("showcase.step1Body"),
    },
    {
      icon: <GitPullRequestArrow className="size-4" />,
      title: t("showcase.step2Title"),
      body: t("showcase.step2Body"),
    },
    {
      icon: <ShieldCheck className="size-4" />,
      title: t("showcase.step3Title"),
      body: t("showcase.step3Body"),
    },
  ];

  return (
    <section
      id="agent"
      className="relative scroll-mt-24 border-y border-rule bg-paper-deep/50 py-24 sm:py-32"
    >
      <div className="mx-auto grid max-w-6xl items-center gap-14 px-5 sm:px-8 lg:grid-cols-2 lg:gap-20">
        <div ref={left} className="reveal min-w-0">
          <SectionEyebrow>{t("showcase.eyebrow")}</SectionEyebrow>
          <h2 className="mt-4 font-display text-3xl font-normal leading-tight tracking-tight text-ink sm:text-[2.7rem]">
            {t("showcase.titlePre")} <em className="italic text-ink">{t("showcase.titleEm")}</em>{" "}
            {t("showcase.titlePost")}
          </h2>
          <p className="mt-4 max-w-lg text-base leading-relaxed text-ink-soft">
            {t("showcase.intro")}
          </p>

          <ol className="mt-10 space-y-7">
            {steps.map((s, i) => (
              <li key={s.title} className="flex gap-4">
                <span className="relative mt-0.5 inline-flex size-9 shrink-0 items-center justify-center rounded-lg border border-rule bg-paper text-ink">
                  {s.icon}
                  <span className="absolute -right-1.5 -top-1.5 flex h-[18px] w-[18px] items-center justify-center rounded-full bg-ink font-mono text-[0.55rem] text-paper">
                    {i + 1}
                  </span>
                </span>
                <div>
                  <h3 className="font-display text-lg font-medium tracking-tight text-ink">
                    {s.title}
                  </h3>
                  <p className="mt-1 max-w-md text-sm leading-relaxed text-ink-soft">{s.body}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>

        {/* Static multi-hunk review card. */}
        <div
          ref={right}
          className="reveal min-w-0"
          style={{ "--reveal-delay": "120ms" } as CSSProperties}
        >
          <ReviewCard />
        </div>
      </div>
    </section>
  );
}

function ReviewCard() {
  const { t } = useTranslation("landing");
  return (
    <div className="relative">
      <span className="float-soft pointer-events-none absolute -left-4 -top-4 hidden rounded-full border border-rule bg-paper px-3 py-1 text-xs text-ink-soft shadow-sm sm:block">
        {t("showcase.reviewLabel")}
      </span>
      <div className="overflow-hidden rounded-2xl border border-rule bg-[hsl(36_30%_99%)] shadow-[0_40px_80px_-50px_hsl(var(--ink)/0.55)]">
        <div className="flex items-center justify-between border-b border-rule/80 bg-paper-deep/50 px-4 py-2.5 text-xs">
          <span className="font-mono text-ink-soft">main.tex</span>
          <span className="text-emerald-700">+4 −5</span>
        </div>

        <pre className="overflow-x-auto px-4 py-3 font-mono text-[0.7rem] leading-relaxed">
          <DiffLine type="ctx" n="14">
            {"  We evaluate the approach on three datasets."}
          </DiffLine>
          <DiffLine type="del" n="15">
            {"  The results clearly and unambiguously show that"}
          </DiffLine>
          <DiffLine type="del" n="16">
            {"  our method is substantially better in every case."}
          </DiffLine>
          <DiffLine type="add" n="15">
            {"  Our method outperforms the baselines on all three."}
          </DiffLine>
          <DiffLine type="ctx" n="17">
            {""}
          </DiffLine>
          <DiffLine type="ctx" n="18">
            {"  \\subsection{Ablations}"}
          </DiffLine>
          <DiffLine type="del" n="19">
            {"  We did a lot of ablation experiments here."}
          </DiffLine>
          <DiffLine type="add" n="18">
            {"  We ablate each component in Table~\\ref{tab:abl}."}
          </DiffLine>
        </pre>

        <div className="flex items-center gap-2 border-t border-rule/80 px-4 py-3">
          <span className="inline-flex items-center gap-1.5 rounded-md bg-ink px-3 py-1.5 text-xs font-medium text-paper">
            <Check className="size-3.5" /> {t("showcase.apply")}
          </span>
          <span className="inline-flex items-center gap-1.5 rounded-md border border-rule px-3 py-1.5 text-xs font-medium text-ink-soft">
            <X className="size-3.5" /> {t("showcase.skip")}
          </span>
          <span className="ml-auto text-[0.7rem] text-ink-faint">{t("showcase.hunkOf")}</span>
        </div>
      </div>
    </div>
  );
}

function DiffLine({
  type,
  n,
  children,
}: {
  type: "ctx" | "add" | "del";
  n: string;
  children: ReactNode;
}) {
  const tone =
    type === "add"
      ? "bg-emerald-500/10 text-emerald-800"
      : type === "del"
        ? "bg-rose-500/10 text-rose-700/90"
        : "text-ink-soft";
  const sign = type === "add" ? "+" : type === "del" ? "−" : " ";
  const signTone =
    type === "add" ? "text-emerald-500" : type === "del" ? "text-rose-400" : "text-transparent";
  return (
    <div className={`-mx-4 flex gap-3 px-4 ${tone}`}>
      <span className="w-5 shrink-0 select-none text-right text-ink-faint/50">{n}</span>
      <span className={`shrink-0 select-none ${signTone}`}>{sign}</span>
      <span className="whitespace-pre">{children}</span>
    </div>
  );
}
