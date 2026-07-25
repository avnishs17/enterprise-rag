import { FileText } from "lucide-react";

interface SourcesPanelProps {
  sources: string[];
}

function parseSource(source: string, index: number) {
  const match = source.match(/^\[(S\d+)] SOURCE: ([^\n]+)\nCONTENT:\s*([\s\S]*)$/);
  return match
    ? { label: match[1], title: match[2], content: match[3] }
    : { label: `S${index + 1}`, title: `Retrieved chunk ${index + 1}`, content: source };
}

export function SourcesPanel({ sources }: SourcesPanelProps) {
  return (
    <div className="mt-2 border-t border-zinc-700/50 pt-2">
      <details className="group">
        <summary className="flex cursor-pointer items-center gap-1.5 text-xs text-zinc-400 hover:text-zinc-300">
          <FileText className="h-3 w-3" />
          Sources ({sources.length} chunks)
        </summary>
        <div className="mt-2 space-y-2">
          {sources.map((rawSource, index) => {
            const source = parseSource(rawSource, index);
            return (
              <details key={`${source.label}-${index}`} className="rounded-lg bg-zinc-800 p-2">
                <summary className="cursor-pointer text-xs text-zinc-400 hover:text-zinc-300">
                  [{source.label}] {source.title}
                </summary>
                <pre className="mt-1 whitespace-pre-wrap text-xs text-zinc-300">{source.content}</pre>
              </details>
            );
          })}
        </div>
      </details>
    </div>
  );
}
