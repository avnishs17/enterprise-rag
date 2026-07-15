import { FileText } from "lucide-react";

interface SourcesPanelProps {
  sources: string[];
}

export function SourcesPanel({ sources }: SourcesPanelProps) {
  return (
    <div className="mt-2 border-t border-zinc-700/50 pt-2">
      <details className="group">
        <summary className="flex cursor-pointer items-center gap-1.5 text-xs text-zinc-400 hover:text-zinc-300">
          <FileText className="h-3 w-3" />
          Retrieved context ({sources.length} chunks)
        </summary>
        <div className="mt-2 space-y-2">
          {sources.map((source, i) => (
            <details key={i} className="rounded-lg bg-zinc-800 p-2">
              <summary className="cursor-pointer text-xs text-zinc-400 hover:text-zinc-300">
                Chunk {i + 1}: {source.slice(0, 80).replace(/\n/g, " ")}...
              </summary>
              <pre className="mt-1 whitespace-pre-wrap text-xs text-zinc-300">
                {source}
              </pre>
            </details>
          ))}
        </div>
      </details>
    </div>
  );
}
