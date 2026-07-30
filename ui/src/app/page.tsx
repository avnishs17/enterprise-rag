"use client";

import { useEffect, useState } from "react";
import { Sidebar } from "../components/layout/Sidebar";
import { ChatContainer } from "../components/chat/ChatContainer";

function createThreadId(): string {
  if (typeof globalThis.crypto?.randomUUID === "function") {
    return globalThis.crypto.randomUUID();
  }
  return `thread-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

export default function Home() {
  const [threadId, setThreadId] = useState("");

  useEffect(() => {
    setThreadId(createThreadId());
  }, []);

  return (
    <div className="flex h-screen">
      <Sidebar threadId={threadId} />
      <main className="flex flex-1 flex-col">
        {threadId && <ChatContainer threadId={threadId} onThreadChange={setThreadId} />}
      </main>
    </div>
  );
}
