import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface MarkdownContentProps {
  content: string;
}

/** Render model output as safe GitHub-flavored Markdown (raw HTML is not enabled). */
export function MarkdownContent({ content }: MarkdownContentProps) {
  return (
    <div className="break-words text-sm leading-relaxed">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p className="my-2 first:mt-0 last:mb-0">{children}</p>,
          h1: ({ children }) => <h1 className="mb-2 mt-4 text-xl font-semibold first:mt-0">{children}</h1>,
          h2: ({ children }) => <h2 className="mb-2 mt-4 text-lg font-semibold first:mt-0">{children}</h2>,
          h3: ({ children }) => <h3 className="mb-1 mt-3 font-semibold first:mt-0">{children}</h3>,
          ul: ({ children }) => <ul className="my-2 list-disc space-y-1 pl-5">{children}</ul>,
          ol: ({ children }) => <ol className="my-2 list-decimal space-y-1 pl-5">{children}</ol>,
          li: ({ children }) => <li>{children}</li>,
          blockquote: ({ children }) => (
            <blockquote className="my-2 border-l-2 border-zinc-500 pl-3 text-zinc-300">{children}</blockquote>
          ),
          a: ({ children, href }) => (
            <a
              href={href}
              target="_blank"
              rel="noreferrer"
              className="text-blue-400 underline underline-offset-2 hover:text-blue-300"
            >
              {children}
            </a>
          ),
          code: ({ children, className }) => {
            const isBlock = Boolean(className);
            return isBlock ? (
              <code className={className}>{children}</code>
            ) : (
              <code className="rounded bg-zinc-950 px-1 py-0.5 font-mono text-[0.85em] text-zinc-200">{children}</code>
            );
          },
          pre: ({ children }) => (
            <pre className="my-2 overflow-x-auto rounded-lg bg-zinc-950 p-3 text-xs text-zinc-200">{children}</pre>
          ),
          hr: () => <hr className="my-3 border-zinc-700" />,
          table: ({ children }) => <div className="my-2 overflow-x-auto"><table className="w-full border-collapse text-xs">{children}</table></div>,
          th: ({ children }) => <th className="border border-zinc-700 bg-zinc-900 px-2 py-1 text-left font-semibold">{children}</th>,
          td: ({ children }) => <td className="border border-zinc-700 px-2 py-1 align-top">{children}</td>,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
