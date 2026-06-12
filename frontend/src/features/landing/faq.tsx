import { Plus } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";

import { SectionEyebrow } from "./feature-grid";
import { useReveal } from "./use-reveal";

const ITEM_KEYS = ["1", "2", "3", "4", "5", "6"] as const;

export function Faq() {
  const { t } = useTranslation("landing");
  const head = useReveal<HTMLDivElement>();
  const [open, setOpen] = useState<number | null>(0);

  const items = ITEM_KEYS.map((k) => ({ q: t(`faq.q${k}`), a: t(`faq.a${k}`) }));

  return (
    <section
      id="faq"
      className="relative scroll-mt-24 border-t border-rule bg-paper-deep/40 py-24 sm:py-32"
    >
      <div className="mx-auto grid max-w-6xl gap-12 px-5 sm:px-8 lg:grid-cols-[0.8fr_1.2fr] lg:gap-20">
        <div ref={head} className="reveal lg:sticky lg:top-28 lg:self-start">
          <SectionEyebrow>{t("faq.eyebrow")}</SectionEyebrow>
          <h2 className="mt-4 font-display text-3xl font-normal leading-tight tracking-tight text-ink sm:text-[2.6rem]">
            {t("faq.title")}
          </h2>
          <p className="mt-4 max-w-sm text-base leading-relaxed text-ink-soft">
            {t("faq.subhead")}
          </p>
        </div>

        <ul className="divide-y divide-rule border-y border-rule">
          {items.map((item, i) => {
            const isOpen = open === i;
            return (
              <li key={i}>
                <button
                  type="button"
                  onClick={() => setOpen(isOpen ? null : i)}
                  aria-expanded={isOpen}
                  className="flex w-full items-start gap-4 py-5 text-left"
                >
                  <span className="flex-1 font-display text-lg font-medium tracking-tight text-ink">
                    {item.q}
                  </span>
                  <Plus
                    className={cn(
                      "mt-1 size-5 shrink-0 text-ink-faint transition-transform duration-300",
                      isOpen && "rotate-45",
                    )}
                  />
                </button>
                <div
                  className={cn(
                    "grid transition-all duration-300 ease-out",
                    isOpen ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0",
                  )}
                >
                  <div className="overflow-hidden">
                    <p className="max-w-xl pb-5 text-sm leading-relaxed text-ink-soft">{item.a}</p>
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}
