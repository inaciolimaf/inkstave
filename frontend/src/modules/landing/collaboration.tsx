import { MousePointer2, Radio, Share2 } from "lucide-react";
import type { CSSProperties, ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";

import { SectionEyebrow } from "./feature-grid";
import { useReveal } from "./use-reveal";

const PEOPLE = [
  { name: "Mara", color: "bg-rose-500", initial: "M" },
  { name: "Theo", color: "bg-sky-600", initial: "T" },
  { name: "Iris", color: "bg-amber-500", initial: "I" },
];

export function Collaboration() {
  const { t } = useTranslation("landing");
  const head = useReveal<HTMLDivElement>();
  const visual = useReveal<HTMLDivElement>();

  const points = [
    {
      icon: <Radio className="size-4" />,
      title: t("collab.point1Title"),
      body: t("collab.point1Body"),
    },
    {
      icon: <MousePointer2 className="size-4" />,
      title: t("collab.point2Title"),
      body: t("collab.point2Body"),
    },
    {
      icon: <Share2 className="size-4" />,
      title: t("collab.point3Title"),
      body: t("collab.point3Body"),
    },
  ];

  return (
    <section id="collaboration" className="relative scroll-mt-24 py-24 sm:py-32">
      <div className="mx-auto max-w-6xl px-5 sm:px-8">
        <div ref={head} className="reveal mx-auto max-w-2xl text-center">
          <div className="flex justify-center">
            <SectionEyebrow>{t("collab.eyebrow")}</SectionEyebrow>
          </div>
          <h2 className="mt-4 font-display text-3xl font-normal leading-tight tracking-tight text-ink sm:text-[2.7rem]">
            {t("collab.title")}
          </h2>
          <p className="mx-auto mt-4 max-w-xl text-base leading-relaxed text-ink-soft">
            {t("collab.subPre")}
            <span className="font-mono text-[0.85em]">final_v3_FINAL.tex</span>
            {t("collab.subPost")}
          </p>
        </div>

        <div
          ref={visual}
          className="reveal mx-auto mt-14 max-w-3xl"
          style={{ "--reveal-delay": "100ms" } as CSSProperties}
        >
          <div className="overflow-hidden rounded-2xl border border-rule bg-[hsl(36_30%_99%)] shadow-[0_40px_80px_-50px_hsl(var(--ink)/0.5)]">
            {/* Presence bar */}
            <div className="flex items-center gap-3 border-b border-rule/80 bg-paper-deep/50 px-4 py-2.5">
              <span className="text-xs font-mono text-ink-soft">proposal.tex</span>
              <div className="ml-auto flex items-center gap-2">
                <div className="flex -space-x-2">
                  {PEOPLE.map((p) => (
                    <span
                      key={p.name}
                      className={cn(
                        "inline-flex size-6 items-center justify-center rounded-full border-2 border-paper text-[0.62rem] font-semibold text-white",
                        p.color,
                      )}
                    >
                      {p.initial}
                    </span>
                  ))}
                </div>
                <span className="text-[0.7rem] text-ink-faint">{t("collab.editing")}</span>
              </div>
            </div>

            {/* Paragraph with live cursors */}
            <div className="relative px-6 py-7 font-mono text-[0.78rem] leading-[2.1] text-ink-soft">
              <p>
                We propose a method that
                <Cursor name="Mara" color="bg-rose-500" />
                &nbsp;converges quickly and remains robust under noise. In
                <Cursor name="Theo" color="bg-sky-600" delay="1.1s" />
                &nbsp;practice it scales to large corpora without
                <Cursor name="Iris" color="bg-amber-500" delay="0.5s" />
                &nbsp;loss of accuracy.
              </p>
            </div>
          </div>
        </div>

        <div className="mx-auto mt-12 grid max-w-4xl gap-6 sm:grid-cols-3">
          {points.map((p, i) => (
            <Point key={p.title} {...p} delay={i * 80} />
          ))}
        </div>
      </div>
    </section>
  );
}

function Point({
  icon,
  title,
  body,
  delay,
}: {
  icon: ReactNode;
  title: string;
  body: string;
  delay: number;
}) {
  const ref = useReveal<HTMLDivElement>();
  return (
    <div ref={ref} className="reveal" style={{ "--reveal-delay": `${delay}ms` } as CSSProperties}>
      <span className="inline-flex size-9 items-center justify-center rounded-lg border border-rule bg-paper-deep/50 text-ink">
        {icon}
      </span>
      <h3 className="mt-3 font-display text-lg font-medium tracking-tight text-ink">{title}</h3>
      <p className="mt-1.5 text-sm leading-relaxed text-ink-soft">{body}</p>
    </div>
  );
}

function Cursor({ name, color, delay }: { name: string; color: string; delay?: string }) {
  return (
    <span className="relative inline-block align-baseline">
      <span className={cn("inline-block h-[1.2em] w-px translate-y-[3px]", color)} />
      <span
        className={cn(
          "cursor-bob absolute -top-5 left-0 whitespace-nowrap rounded px-1.5 py-0.5 text-[0.58rem] font-medium text-white",
          color,
        )}
        style={delay ? ({ animationDelay: delay } as CSSProperties) : undefined}
      >
        {name}
      </span>
    </span>
  );
}
