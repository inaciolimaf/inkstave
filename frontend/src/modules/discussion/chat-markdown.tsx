/** A chat message as Markdown: no raw HTML, and every link opens in a new tab (spec 117). */
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

const components: Components = {
  // A message sits inside a screen with its own headings: every heading shrinks to a bold line.
  h1: (p) => <p className="font-semibold" {...p} />,
  h2: (p) => <p className="font-semibold" {...p} />,
  h3: (p) => <p className="font-semibold" {...p} />,
  // Plain newlines in a message stay line breaks.
  p: (p) => <p className="my-0.5 whitespace-pre-wrap break-words" {...p} />,
  a: (p) => (
    <a
      className="text-primary underline underline-offset-2"
      target="_blank"
      rel="noopener noreferrer"
      {...p}
    />
  ),
  ul: (p) => <ul className="my-0.5 list-disc pl-5" {...p} />,
  ol: (p) => <ol className="my-0.5 list-decimal pl-5" {...p} />,
  li: (p) => <li className="my-0.5" {...p} />,
  blockquote: (p) => <blockquote className="my-0.5 border-l-2 pl-3 text-muted-foreground" {...p} />,
  // Images are not loaded from a message; their alt text stands in for them.
  img: ({ alt }) => <span className="italic">{alt}</span>,
  code: (p) => <code className="font-mono text-small" {...p} />,
  pre: (p) => <pre className="my-0.5 overflow-x-auto font-mono text-small" {...p} />,
};

export function ChatMarkdown({ children }: { children: string }) {
  return (
    <div className="min-w-0 break-words text-body">
      <ReactMarkdown skipHtml remarkPlugins={[remarkGfm]} components={components}>
        {children}
      </ReactMarkdown>
    </div>
  );
}
