"use client";

import { cn } from "../../lib/utils";
import type { ChatMessage as ChatMessageType } from "../../lib/types";
import { ThoughtProcess } from "./ThoughtProcess";
import { SourcesPanel } from "./SourcesPanel";
import { MarkdownContent } from "./MarkdownContent";

const SOURCE_LABELS: Record<string, { label: string; color: string }> = {
  memory: { label: "Memory", color: "bg-violet-600" },
  rag_documents: { label: "RAG", color: "bg-emerald-600" },
  conversation_history: { label: "History", color: "bg-amber-600" },
};

interface ChatMessageProps {
  message: ChatMessageType;
}

export function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === "user";

  return (
    <div
      className={cn(
        "flex w-full gap-3 px-4 py-3",
        isUser ? "justify-end" : "justify-start",
      )}
    >
      <div
        className={cn(
          "flex max-w-[80%] flex-col gap-1.5 rounded-2xl px-4 py-2.5",
          isUser
            ? "bg-blue-600 text-white"
            : "bg-zinc-800 text-zinc-100",
        )}
      >
        {message.content ? (
          isUser ? (
            <p className="whitespace-pre-wrap text-sm leading-relaxed">{message.content}</p>
          ) : (
            <MarkdownContent content={message.content} />
          )
        ) : (
          <span className="text-sm opacity-50">Generating response...</span>
        )}

        {!isUser && message.sourcesUsed && message.sourcesUsed.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-1">
            {message.sourcesUsed.map((s) => {
              const info = SOURCE_LABELS[s];
              if (!info) return null;
              return (
                <span
                  key={s}
                  className={cn(
                    "px-2 py-0.5 rounded-full text-[10px] font-medium text-white",
                    info.color,
                  )}
                >
                  {info.label}
                </span>
              );
            })}
          </div>
        )}

        {!isUser && message.thoughtProcess && message.thoughtProcess.length > 0 && (
          <ThoughtProcess steps={message.thoughtProcess} />
        )}

        {!isUser && message.sources && message.sources.length > 0 && (
          <SourcesPanel sources={message.sources} />
        )}
      </div>
    </div>
  );
}
