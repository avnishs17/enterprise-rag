"use client";

import { type FormEvent, useRef } from "react";
import { Send, Loader2 } from "lucide-react";
import { cn } from "../../lib/utils";

interface ChatInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
}

export function ChatInput({ onSend, disabled }: ChatInputProps) {
  const inputRef = useRef<HTMLTextAreaElement>(null);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const value = inputRef.current?.value.trim();
    if (!value) return;

    onSend(value);
    if (inputRef.current) {
      inputRef.current.value = "";
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex items-end gap-2">
      <textarea
        ref={inputRef}
        rows={1}
        placeholder="Ask about your documentation..."
        disabled={disabled}
        onKeyDown={handleKeyDown}
        className={cn(
          "min-h-[44px] w-full resize-none rounded-xl border border-zinc-700",
          "bg-zinc-800/50 px-4 py-2.5 text-sm text-zinc-100",
          "placeholder:text-zinc-500",
          "focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500",
          "disabled:cursor-not-allowed disabled:opacity-50",
        )}
      />
      <button
        type="submit"
        disabled={disabled}
        className={cn(
          "flex h-[44px] w-[44px] shrink-0 items-center justify-center rounded-xl",
          "bg-blue-600 text-white transition-colors",
          "hover:bg-blue-700 active:bg-blue-800",
          "disabled:cursor-not-allowed disabled:opacity-50",
        )}
      >
        {disabled ? (
          <Loader2 className="h-5 w-5 animate-spin" />
        ) : (
          <Send className="h-5 w-5" />
        )}
      </button>
    </form>
  );
}
