"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { deleteConversation, queryStream } from "../lib/api";
import type { ChatMessage } from "../lib/types";

function generateId(): string {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
}

interface UseChatOptions {
  threadId: string;
  onThreadChange: (threadId: string) => void;
}

interface UseChatReturn {
  messages: ChatMessage[];
  isPending: boolean;
  error: string | null;
  sendMessage: (content: string) => Promise<void>;
  clearHistory: () => Promise<void>;
}

export function useChat({ threadId: externalThreadId, onThreadChange }: UseChatOptions): UseChatReturn {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const threadIdRef = useRef<string>(externalThreadId);
  const abortRef = useRef<AbortController | null>(null);
  const pendingRef = useRef(false);
  const tokenQueueRef = useRef<string[]>([]);
  const flushTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    threadIdRef.current = externalThreadId;
  }, [externalThreadId]);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      if (flushTimerRef.current) clearTimeout(flushTimerRef.current);
    };
  }, []);

  const sendMessage = useCallback(async (content: string) => {
    if (!content.trim()) return;
    if (pendingRef.current) return;

    pendingRef.current = true;
    setIsPending(true);
    setError(null);

    const userMessage: ChatMessage = {
      id: generateId(),
      role: "user",
      content: content.trim(),
    };

    setMessages((prev) => [...prev, userMessage]);

    const assistantId = generateId();
    const assistantMessage: ChatMessage = {
      id: assistantId,
      role: "assistant",
      content: "",
      thoughtProcess: [],
      sources: [],
    };

    setMessages((prev) => [...prev, assistantMessage]);

    const abortController = new AbortController();
    abortRef.current = abortController;

    const flushTokens = () => {
      flushTimerRef.current = null;
      const tokens = tokenQueueRef.current;
      tokenQueueRef.current = [];
      if (tokens.length === 0) return;
      const chunk = tokens.join("");
      setMessages((prev) => {
        const updated = [...prev];
        const last = updated[updated.length - 1];
        if (last && last.role === "assistant" && last.id === assistantId) {
          updated[updated.length - 1] = {
            ...last,
            content: last.content + chunk,
          };
        }
        return updated;
      });
    };

    try {
      const stream = queryStream(
        { q: content.trim(), thread_id: threadIdRef.current },
        abortController.signal,
      );

      for await (const event of stream) {
        switch (event.event) {
          case "thought":
            // flush any pending tokens first so thought steps appear after current text
            if (flushTimerRef.current) {
              clearTimeout(flushTimerRef.current);
              flushTokens();
            }
            setMessages((prev) => {
              const updated = [...prev];
              const last = updated[updated.length - 1];
              if (last && last.role === "assistant" && last.id === assistantId) {
                updated[updated.length - 1] = {
                  ...last,
                  thoughtProcess: [...(last.thoughtProcess || []), event.data.content],
                };
              }
              return updated;
            });
            break;

          case "token":
            tokenQueueRef.current.push(event.data.content);
            if (!flushTimerRef.current) {
              flushTimerRef.current = setTimeout(flushTokens, 15);
            }
            break;

          case "source":
            setMessages((prev) => {
              const updated = [...prev];
              const last = updated[updated.length - 1];
              if (last && last.role === "assistant" && last.id === assistantId) {
                updated[updated.length - 1] = {
                  ...last,
                  sources: event.data.chunks,
                };
              }
              return updated;
            });
            break;

          case "error":
            setError(event.data.message);
            abortController.abort();
            break;

          case "done":
            if (flushTimerRef.current) {
              clearTimeout(flushTimerRef.current);
              flushTokens();
            }
            setMessages((prev) => {
              const updated = [...prev];
              const last = updated[updated.length - 1];
              if (last && last.role === "assistant" && last.id === assistantId) {
                updated[updated.length - 1] = {
                  ...last,
                  sourcesUsed: event.data.sources_used,
                };
              }
              return updated;
            });
            break;
        }
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;

      const message = err instanceof Error ? err.message : "An unexpected error occurred";
      setError(message);

      setMessages((prev) => {
        const updated = [...prev];
        const last = updated[updated.length - 1];
        if (last && last.role === "assistant" && last.id === assistantId && !last.content) {
          updated[updated.length - 1] = {
            ...last,
            content: `Error: ${message}`,
          };
        }
        return updated;
      });
    } finally {
      if (flushTimerRef.current) {
        clearTimeout(flushTimerRef.current);
        flushTokens();
      }
      setIsPending(false);
      pendingRef.current = false;
      abortRef.current = null;
    }
  }, []);

  const clearHistory = useCallback(async () => {
    const previousThreadId = threadIdRef.current;
    abortRef.current?.abort();
    const nextThreadId = generateId();
    threadIdRef.current = nextThreadId;
    onThreadChange(nextThreadId);
    setMessages([]);
    setError(null);
    setIsPending(false);
    pendingRef.current = false;

    try {
      await deleteConversation(previousThreadId);
    } catch {
      setError("The local chat was cleared, but its server history could not be deleted.");
    }
  }, [onThreadChange]);

  return { messages, isPending, error, sendMessage, clearHistory };
}
