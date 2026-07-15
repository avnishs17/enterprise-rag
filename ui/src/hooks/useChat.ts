"use client";

import { useCallback, useRef, useState } from "react";
import { query } from "../lib/api";
import type { ChatMessage, QueryResponse } from "../lib/types";

function generateId(): string {
  return crypto.randomUUID();
}

interface UseChatOptions {
  threadId?: string;
}

interface UseChatReturn {
  messages: ChatMessage[];
  isPending: boolean;
  error: string | null;
  sendMessage: (content: string) => Promise<void>;
  clearHistory: () => void;
}

export function useChat({ threadId: externalThreadId }: UseChatOptions = {}): UseChatReturn {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const threadIdRef = useRef<string>(externalThreadId || generateId());
  const abortRef = useRef<AbortController | null>(null);

  const sendMessage = useCallback(async (content: string) => {
    if (!content.trim() || isPending) return;

    setError(null);

    const userMessage: ChatMessage = {
      id: generateId(),
      role: "user",
      content: content.trim(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setIsPending(true);

    const assistantMessage: ChatMessage = {
      id: generateId(),
      role: "assistant",
      content: "",
    };

    setMessages((prev) => [...prev, assistantMessage]);

    abortRef.current = new AbortController();

    try {
      const data = await query(
        { q: content.trim(), thread_id: threadIdRef.current },
        abortRef.current.signal,
      );

      setMessages((prev) => {
        const updated = [...prev];
        const last = updated[updated.length - 1];
        if (last && last.role === "assistant" && last.id === assistantMessage.id) {
          updated[updated.length - 1] = {
            ...last,
            content: data.answer,
            thoughtProcess: data.thought_process,
            sources: data.sources,
          };
        }
        return updated;
      });
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;

      const message = err instanceof Error ? err.message : "An unexpected error occurred";
      setError(message);

      setMessages((prev) => {
        const updated = [...prev];
        const last = updated[updated.length - 1];
        if (last && last.role === "assistant" && last.id === assistantMessage.id) {
          updated[updated.length - 1] = {
            ...last,
            content: `Error: ${message}`,
          };
        }
        return updated;
      });
    } finally {
      setIsPending(false);
      abortRef.current = null;
    }
  }, [isPending]);

  const clearHistory = useCallback(() => {
    abortRef.current?.abort();
    threadIdRef.current = generateId();
    setMessages([]);
    setError(null);
    setIsPending(false);
  }, []);

  return { messages, isPending, error, sendMessage, clearHistory };
}
