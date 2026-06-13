import { ArrowRight, Check, FileText, Search, Sparkles, X } from "lucide-react";
import type { HTMLAttributes, ReactNode } from "react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";

/*
 * A fully *scripted* re-creation of the Inkstave agent at work — no network, no
 * tokens, no real LLM. It loops through: the user asks, the agent searches and
 * reads the project, proposes a unified diff, and the user accepts it, at which
 * point the document text updates. Every step is a timed state change so the
 * hero communicates the product in a few seconds. Honours reduced-motion by
 * jumping straight to the "applied" rest state.
 */

// Sample document content stays in English — it's a fake LaTeX abstract, not UI.
const ABSTRACT_BEFORE = [
  "We present a comprehensive and exhaustive overview of",
  "the proposed method, describing in great detail every",
  "step of the pipeline and each of its many parameters.",
];

const ABSTRACT_AFTER = [
  "We present a concise overview of the proposed method",
  "and its pipeline, detailing each component in turn.",
];

type Phase = "prompt" | "reading" | "reply" | "diff" | "applying" | "applied";

interface DemoState {
  phase: Phase;
  typed: number; // chars of the prompt revealed
  chips: number; // tool chips shown (0–2)
}

function prefersReducedMotion() {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

export function AgentDemo() {
  const { t } = useTranslation("landing");
  const prompt = t("demo.prompt");
  const [state, setState] = useState<DemoState>({ phase: "prompt", typed: 0, chips: 0 });
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  useEffect(() => {
    if (prefersReducedMotion()) {
      setState({ phase: "applied", typed: prompt.length, chips: 2 });
      return;
    }

    const queue = timers.current;
    const after = (ms: number, fn: () => void) => queue.push(setTimeout(fn, ms));

    const runCycle = () => {
      setState({ phase: "prompt", typed: 0, chips: 0 });

      // 1. Type the prompt out, char by char.
      const typeStep = (i: number) => {
        setState((s) => ({ ...s, typed: i }));
        if (i < prompt.length) {
          after(34, () => typeStep(i + 1));
        } else {
          after(520, beginReading);
        }
      };

      // 2. Agent searches, then reads.
      const beginReading = () => {
        setState((s) => ({ ...s, phase: "reading", chips: 1 }));
        after(820, () => setState((s) => ({ ...s, chips: 2 })));
        after(1700, beginReply);
      };

      // 3. Agent replies, then 4. shows the diff.
      const beginReply = () => {
        setState((s) => ({ ...s, phase: "reply" }));
        after(900, () => setState((s) => ({ ...s, phase: "diff" })));
        after(2700, accept);
      };

      // 5. Accept → 6. applied, then loop.
      const accept = () => {
        setState((s) => ({ ...s, phase: "applying" }));
        after(560, () => setState((s) => ({ ...s, phase: "applied" })));
        after(3800, runCycle);
      };

      typeStep(0);
    };

    runCycle();
    return () => {
      queue.forEach(clearTimeout);
      queue.length = 0;
    };
  }, [prompt]);

  const applied = state.phase === "applied";
  const lines = applied ? ABSTRACT_AFTER : ABSTRACT_BEFORE;

  return (
    <div className="grid gap-3 sm:grid-cols-[1.05fr_0.95fr]">
      {/* Editor pane */}
      <figure className="overflow-hidden rounded-xl border border-rule bg-[hsl(36_30%_99%)] shadow-[0_1px_0_hsl(var(--ink)/0.04),0_24px_50px_-30px_hsl(var(--ink)/0.45)]">
        <div className="flex items-center gap-2 border-b border-rule/80 bg-paper-deep/60 px-3.5 py-2">
          <span className="flex gap-1.5">
            <span className="size-2.5 rounded-full bg-rule" />
            <span className="size-2.5 rounded-full bg-rule" />
            <span className="size-2.5 rounded-full bg-rule" />
          </span>
          <span className="ml-1 flex items-center gap-1.5 text-xs text-ink-faint">
            <FileText className="size-3.5" />
            main.tex
          </span>
          <span className="ml-auto flex items-center gap-1.5 text-[0.7rem] font-medium text-emerald-700">
            <span className="size-1.5 rounded-full bg-emerald-500 pulse-dot" />
            {t("demo.live")}
          </span>
        </div>

        <pre className="overflow-x-auto px-4 py-3.5 font-mono text-[0.72rem] leading-[1.65] text-ink">
          <CodeLine n={11}>
            <Tex>{"\\begin{abstract}"}</Tex>
          </CodeLine>
          {lines.map((line, i) => (
            <CodeLine
              key={`${applied ? "a" : "b"}-${i}`}
              n={12 + i}
              className={cn(applied && "rise-in bg-emerald-500/10")}
            >
              {line}
            </CodeLine>
          ))}
          <CodeLine n={12 + lines.length}>
            <Tex>{"\\end{abstract}"}</Tex>
          </CodeLine>
        </pre>
      </figure>

      {/* Agent panel */}
      <div className="flex flex-col overflow-hidden rounded-xl border border-rule bg-paper shadow-[0_1px_0_hsl(var(--ink)/0.04),0_24px_50px_-30px_hsl(var(--ink)/0.45)]">
        <div className="flex items-center gap-2 border-b border-rule/80 px-3.5 py-2.5">
          <Sparkles className="size-3.5 text-ink" />
          <span className="text-xs font-semibold tracking-tight">{t("demo.agent")}</span>
          <span className="ml-auto text-[0.7rem] text-ink-faint">{t("demo.neverEdits")}</span>
        </div>

        {/*
         * The conversation reserves space for its tallest phase (the diff) by
         * stacking an invisible "ghost" of that phase in the same grid cell as
         * the live content. The cell sizes to the ghost at any width, so the
         * panel never grows or shrinks as steps appear — nothing below reflows.
         */}
        <div className="relative grid flex-1">
          <Conversation
            aria-hidden
            className="pointer-events-none invisible select-none [grid-area:1/1]"
            state={{ phase: "diff", typed: prompt.length, chips: 2 }}
          />
          <Conversation className="[grid-area:1/1]" state={state} />
        </div>
      </div>
    </div>
  );
}

/**
 * The agent panel's message thread for a given scripted state. Rendered twice:
 * once live, and once invisibly (forced to the tallest "diff" phase) to reserve
 * a stable height — see the grid stack in AgentDemo.
 */
function Conversation({
  state,
  className,
  ...rest
}: {
  state: DemoState;
  className?: string;
} & HTMLAttributes<HTMLDivElement>) {
  const { t } = useTranslation("landing");
  const prompt = t("demo.prompt");

  return (
    <div
      className={cn("flex flex-col gap-2.5 p-3.5 text-[0.78rem]", className)}
      {...rest}
    >
      {/* User prompt */}
      <div className="self-end rounded-2xl rounded-br-sm bg-ink px-3 py-1.5 text-[0.76rem] text-paper">
        {prompt.slice(0, state.typed)}
        {state.phase === "prompt" && <span className="caret h-[0.9em] align-middle" />}
      </div>

      {/* Tool chips */}
      {state.chips >= 1 && (
        <ToolChip icon={<Search className="size-3" />}>{t("demo.searched")}</ToolChip>
      )}
      {state.chips >= 2 && (
        <ToolChip icon={<FileText className="size-3" />}>{t("demo.read")}</ToolChip>
      )}

      {/* Agent reply */}
      {(state.phase === "reply" ||
        state.phase === "diff" ||
        state.phase === "applying" ||
        state.phase === "applied") && (
        <p className="rise-in max-w-[92%] text-ink-soft">{t("demo.reply")}</p>
      )}

      {/* Diff card */}
      {(state.phase === "diff" || state.phase === "applying") && (
        <div className="rise-in overflow-hidden rounded-lg border border-rule bg-[hsl(36_30%_99%)]">
          <div className="flex items-center justify-between border-b border-rule/80 px-2.5 py-1.5 text-[0.68rem] text-ink-faint">
            <span className="font-mono">main.tex</span>
            <span>1 hunk · +2 −3</span>
          </div>
          <pre className="overflow-x-auto px-2.5 py-2 font-mono text-[0.66rem] leading-relaxed">
            {ABSTRACT_BEFORE.map((l, i) => (
              <div key={`r${i}`} className="text-rose-700/90">
                <span className="mr-1.5 select-none text-rose-400">−</span>
                {l}
              </div>
            ))}
            {ABSTRACT_AFTER.map((l, i) => (
              <div key={`g${i}`} className="text-emerald-700">
                <span className="mr-1.5 select-none text-emerald-500">+</span>
                {l}
              </div>
            ))}
          </pre>
          <div className="flex items-center gap-1.5 border-t border-rule/80 px-2.5 py-2">
            <span
              className={cn(
                "inline-flex items-center gap-1 rounded-md px-2 py-1 text-[0.7rem] font-medium transition-all",
                state.phase === "applying"
                  ? "scale-95 bg-emerald-600 text-white"
                  : "bg-ink text-paper",
              )}
            >
              <Check className="size-3" /> {t("demo.accept")}
            </span>
            <span className="inline-flex items-center gap-1 rounded-md border border-rule px-2 py-1 text-[0.7rem] font-medium text-ink-soft">
              <X className="size-3" /> {t("demo.reject")}
            </span>
            <span className="ml-auto text-[0.66rem] text-ink-faint">{t("demo.hunkOf")}</span>
          </div>
        </div>
      )}

      {/* Applied confirmation */}
      {state.phase === "applied" && (
        <div className="rise-in mt-auto flex items-center gap-1.5 rounded-md bg-emerald-500/12 px-2.5 py-1.5 text-[0.72rem] font-medium text-emerald-800">
          <Check className="size-3.5" /> {t("demo.applied")}
          <ArrowRight className="ml-auto size-3.5 opacity-60" />
        </div>
      )}
    </div>
  );
}

function CodeLine({
  n,
  children,
  className,
}: {
  n: number;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("-mx-1 flex gap-3 rounded px-1", className)}>
      <span className="w-5 shrink-0 select-none text-right text-ink-faint/55">{n}</span>
      <span className="whitespace-pre">{children}</span>
    </div>
  );
}

const ToolChip = ({ icon, children }: { icon: ReactNode; children: ReactNode }) => (
  <span className="rise-in inline-flex w-fit items-center gap-1.5 rounded-full border border-rule bg-paper-deep/60 px-2.5 py-1 text-[0.68rem] text-ink-soft">
    {icon}
    {children}
  </span>
);

/** Minimal LaTeX tinting for the `\command{arg}` lines in the editor pane. */
function Tex({ children }: { children: string }) {
  const parts = children.split(/(\\[a-zA-Z]+|[{}])/g).filter(Boolean);
  return (
    <>
      {parts.map((p, i) => {
        if (p.startsWith("\\"))
          return (
            <span key={i} className="text-indigo-700">
              {p}
            </span>
          );
        if (p === "{" || p === "}")
          return (
            <span key={i} className="text-ink-faint">
              {p}
            </span>
          );
        return (
          <span key={i} className="text-emerald-800">
            {p}
          </span>
        );
      })}
    </>
  );
}
