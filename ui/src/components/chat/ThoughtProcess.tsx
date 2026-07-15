import { Lightbulb } from "lucide-react";

interface ThoughtProcessProps {
  steps: string[];
}

export function ThoughtProcess({ steps }: ThoughtProcessProps) {
  return (
    <div className="mt-2 border-t border-zinc-700/50 pt-2">
      <details className="group">
        <summary className="flex cursor-pointer items-center gap-1.5 text-xs text-zinc-400 hover:text-zinc-300">
          <Lightbulb className="h-3 w-3" />
          Reasoning steps
        </summary>
        <ol className="mt-1 space-y-0.5 pl-4">
          {steps.map((step, i) => (
            <li key={i} className="list-decimal text-xs text-zinc-400">
              {step}
            </li>
          ))}
        </ol>
      </details>
    </div>
  );
}
