"use client";

import { useEffect, useState } from "react";
import { cn } from "../../lib/utils";
import type { ChatMessage as ChatMessageType } from "../../lib/types";
import { ThoughtProcess } from "./ThoughtProcess";
import { SourcesPanel } from "./SourcesPanel";

interface ChatMessageProps {
  message: ChatMessageType;
  isLatest?: boolean;
}

export function ChatMessage({ message, isLatest }: ChatMessageProps) {
  const isUser = message.role === "user";
  const [displayedText, setDisplayedText] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);

  useEffect(() => {
    if (!isLatest || message.role !== "assistant" || !message.content) return;
    if (message.content.startsWith("Error:")) {
      setDisplayedText(message.content);
      return;
    }

    setIsStreaming(true);
    let index = 0;
    setDisplayedText("");

    const interval = setInterval(() => {
      if (index < message.content.length) {
        setDisplayedText(message.content.slice(0, index + 1));
        index++;
      } else {
        clearInterval(interval);
        setIsStreaming(false);
      }
    }, 5);

    return () => clearInterval(interval);
  }, [isLatest, message.content, message.role]);

  const displayContent =
    isLatest && !isUser && isStreaming
      ? displayedText
      : message.content;

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
        <p className="whitespace-pre-wrap text-sm leading-relaxed">
          {displayContent}
          {isStreaming && <span className="animate-pulse">▌</span>}
        </p>

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
