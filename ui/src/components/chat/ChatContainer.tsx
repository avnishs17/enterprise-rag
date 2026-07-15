"use client";

import { useEffect, useRef } from "react";
import { useChat } from "../../hooks/useChat";
import { ChatMessage } from "./ChatMessage";
import { ChatInput } from "./ChatInput";

export function ChatContainer() {
  const { messages, isPending, error, sendMessage, clearHistory } = useChat();
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-zinc-800 px-6 py-3">
        <div>
          <h1 className="text-lg font-semibold text-zinc-100">
            Enterprise Agentic Assistant
          </h1>
          <p className="text-xs text-zinc-500">
            Ask questions about your documentation
          </p>
        </div>
        <button
          onClick={clearHistory}
          className="rounded-lg border border-zinc-700 px-3 py-1.5 text-xs text-zinc-400 transition-colors hover:border-red-600 hover:text-red-400"
        >
          Clear history
        </button>
      </div>

      <div ref={containerRef} className="flex-1 overflow-y-auto py-4">
        {messages.length === 0 && (
          <div className="flex h-full items-center justify-center">
            <div className="text-center">
              <div className="mb-3 text-4xl">🤖</div>
              <p className="text-sm text-zinc-500">
                Ask a technical question to get started.
              </p>
              <p className="mt-1 text-xs text-zinc-600">
                The assistant will search your documentation and provide an
                answer with sources.
              </p>
            </div>
          </div>
        )}

        <div className="space-y-1">
          {messages.map((msg, i) => (
            <ChatMessage
              key={msg.id}
              message={msg}
              isLatest={i === messages.length - 1}
            />
          ))}
        </div>

        {isPending && messages[messages.length - 1]?.role === "assistant" && (
          <div className="flex items-center gap-2 px-4 py-2">
            <div className="flex space-x-1">
              <div className="h-2 w-2 animate-bounce rounded-full bg-zinc-500" />
              <div className="h-2 w-2 animate-bounce rounded-full bg-zinc-500 [animation-delay:0.1s]" />
              <div className="h-2 w-2 animate-bounce rounded-full bg-zinc-500 [animation-delay:0.2s]" />
            </div>
            <span className="text-xs text-zinc-500">Agent is thinking...</span>
          </div>
        )}

        {error && !isPending && (
          <div className="mx-4 rounded-lg border border-red-800 bg-red-900/30 px-4 py-2">
            <p className="text-xs text-red-400">{error}</p>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      <div className="border-t border-zinc-800 p-4">
        <ChatInput onSend={sendMessage} disabled={isPending} />
      </div>
    </div>
  );
}
