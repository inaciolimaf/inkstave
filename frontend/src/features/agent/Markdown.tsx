/** Render an assistant message as GitHub-flavored Markdown (spec 46). */
import type { ComponentPropsWithoutRef } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/utils";

const components: Components = {
  h1: (p) => <h1 className="mt-3 mb-1 text-base font-semibold" {...p} />,
  h2: (p) => <h2 className="mt-3 mb-1 text-sm font-semibold" {...p} />,
  h3: (p) => <h3 className="mt-2 mb-1 text-sm font-semibold" {...p} />,
  p: (p) => <p className="my-1 leading-relaxed" {...p} />,
  ul: (p) => <ul className="my-1 list-disc pl-5" {...p} />,
  ol: (p) => <ol className="my-1 list-decimal pl-5" {...p} />,
  li: (p) => <li className="my-0.5" {...p} />,
  a: (p) => (
    <a
      className="text-primary underline underline-offset-2"
      target="_blank"
      rel="noreferrer"
      {...p}
    />
  ),
  strong: (p) => <strong className="font-semibold" {...p} />,
  blockquote: (p) => (
    <blockquote className="my-1 border-l-2 pl-3 text-muted-foreground italic" {...p} />
  ),
  hr: () => <hr className="my-2 border-border" />,
  table: (p) => (
    <div className="my-1 overflow-x-auto">
      <table className="w-full border-collapse text-xs" {...p} />
    </div>
  ),
  th: (p) => <th className="border px-2 py-1 text-left font-semibold" {...p} />,
  td: (p) => <td className="border px-2 py-1 align-top" {...p} />,
  pre: (p) => (
    <pre
      className="my-1 overflow-x-auto rounded bg-background/60 p-2 font-mono text-xs"
      {...p}
    />
  ),
  code({ className, children, ...rest }: ComponentPropsWithoutRef<"code">) {
    const isBlock = /language-/.test(className ?? "") || String(children ?? "").includes("\n");
    if (isBlock) {
      return (
        <code className={cn("font-mono", className)} {...rest}>
          {children}
        </code>
      );
    }
    return (
      <code className="rounded bg-background/60 px-1 py-0.5 font-mono text-[0.85em]" {...rest}>
        {children}
      </code>
    );
  },
};

export function Markdown({ children }: { children: string }) {
  return (
    <div className="text-sm break-words">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {children}
      </ReactMarkdown>
    </div>
  );
}
