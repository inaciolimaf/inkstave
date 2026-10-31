import { ArrowRight, Check, FileText, Search, Sparkles, X } from "lucide-react";
import type { HTMLAttributes, ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";

import { type DemoState, useDemoScript } from "./use-demo-script";

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

export function AgentDemo() {
  const { t } = useTranslation("landing");
  const prompt = t("demo.prompt");
  const state = useDemoScript(prompt);

  return (
    <div className="grid gap-3 sm:grid-cols-[1.05fr_0.95fr]">
      <EditorPane applied={state.phase === "applied"} />
      <AgentPane state={state} promptLength={prompt.length} />
    </div>
  );
}

function EditorPane({ applied }: { applied: boolean }) {
  const { t } = useTranslation("landing");
  const lines = applied ? ABSTRACT_AFTER : ABSTRACT_BEFORE;

  return (
    <figure className="min-w-0 overflow-hidden rounded-xl border border-rule bg-[hsl(36_30%_99%)] shadow-[0_1px_0_hsl(var(--ink)/0.04),0_24px_50px_-30px_hsl(var(--ink)/0.45)]">
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
        <span className="ml-auto flex items-center gap-1.5 text-[0.7rem] font-medium text-[hsl(var(--ink-added))]">
          <span className="size-1.5 rounded-full bg-[hsl(var(--ink-added-mark))] pulse-dot" />
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
            className={cn(applied && "rise-in bg-[hsl(var(--ink-added-mark)/0.1)]")}
          >
            {line}
          </CodeLine>
        ))}
        <CodeLine n={12 + lines.length}>
          <Tex>{"\\end{abstract}"}</Tex>
        </CodeLine>
      </pre>
    </figure>
  );
}

function AgentPane({ state, promptLength }: { state: DemoState; promptLength: number }) {
  const { t } = useTranslation("landing");

  return (
    <div className="flex min-w-0 flex-col overflow-hidden rounded-xl border border-rule bg-paper shadow-[0_1px_0_hsl(var(--ink)/0.04),0_24px_50px_-30px_hsl(var(--ink)/0.45)]">
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
      <div className="relative grid min-w-0 grid-cols-1 flex-1">
        <Conversation
          aria-hidden
          className="pointer-events-none invisible select-none [grid-area:1/1]"
          state={{ phase: "diff", typed: promptLength, chips: 2 }}
        />
        <Conversation className="[grid-area:1/1]" state={state} />
      </div>
    </div>
  );
}

/**
 * The agent panel's message thread for a given scripted state. Rendered twice:
 * once live, and once invisibly (forced to the tallest "diff" phase) to reserve
 * a stable height — see the grid stack in AgentPane.
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
    <div className={cn("flex flex-col gap-2.5 p-3.5 text-[0.78rem]", className)} {...rest}>
      {/* User prompt */}
      <div className="self-end rounded-2xl rounded-br-sm bg-ink px-3 py-1.5 text-[0.76rem] text-paper">
        {prompt.slice(0, state.typed)}
        {state.phase === "prompt" && <span className="caret h-[0.9em] align-middle" />}
      </div>

      {/* Tool chips */}
      {state.chips >= 1 && <ToolChip icon={<Search className="size-3" />}>{t("demo.searched")}</ToolChip>}
      {state.chips >= 2 && <ToolChip icon={<FileText className="size-3" />}>{t("demo.read")}</ToolChip>}

      {/* Agent reply */}
      {(state.phase === "reply" ||
        state.phase === "diff" ||
        state.phase === "applying" ||
        state.phase === "applied") && <p className="rise-in max-w-[92%] text-ink-soft">{t("demo.reply")}</p>}

      {/* Diff card */}
      {(state.phase === "diff" || state.phase === "applying") && <DiffCard phase={state.phase} />}

      {/* Applied confirmation */}
      {state.phase === "applied" && (
        <div className="rise-in mt-auto flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[0.72rem] font-medium text-[hsl(var(--ink-added-deep))]">
          <Check className="size-3.5" /> {t("demo.applied")}
          <ArrowRight className="ml-auto size-3.5 opacity-60" />
        </div>
      )}
    </div>
  );
}

function DiffCard({ phase }: { phase: DemoState["phase"] }) {
  const { t } = useTranslation("landing");

  return (
    <div className="rise-in overflow-hidden rounded-lg border border-rule bg-[hsl(36_30%_99%)]">
      <div className="flex items-center justify-between border-b border-rule/80 px-2.5 py-1.5 text-[0.68rem] text-ink-faint">
        <span className="font-mono">main.tex</span>
        <span>1 hunk · +2 −3</span>
      </div>
      <pre className="overflow-x-auto px-2.5 py-2 font-mono text-[0.66rem] leading-relaxed">
        {ABSTRACT_BEFORE.map((l, i) => (
          <div key={`r${i}`} className="text-[hsl(var(--ink-removed)/0.9)]">
            <span className="mr-1.5 select-none text-[hsl(var(--ink-removed-mark))]">−</span>
            {l}
          </div>
        ))}
        {ABSTRACT_AFTER.map((l, i) => (
          <div key={`g${i}`} className="text-[hsl(var(--ink-added))]">
            <span className="mr-1.5 select-none text-[hsl(var(--ink-added-mark))]">+</span>
            {l}
          </div>
        ))}
      </pre>
      <div className="flex items-center gap-1.5 border-t border-rule/80 px-2.5 py-2">
        <span
          className={cn(
            "inline-flex items-center gap-1 rounded-md px-2 py-1 text-[0.7rem] font-medium transition-all",
            phase === "applying"
              ? "scale-95 bg-[hsl(var(--ink-added-solid))] text-[hsl(var(--on-accent))]"
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
  );
}

function CodeLine({ n, children, className }: { n: number; children: ReactNode; className?: string }) {
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
            <span key={i} className="text-[hsl(var(--ink-command))]">
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
          <span key={i} className="text-[hsl(var(--ink-added-deep))]">
            {p}
          </span>
        );
      })}
    </>
  );
}
