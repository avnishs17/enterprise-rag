"use client";

import { useEffect, useState } from "react";
import { Sidebar } from "../components/layout/Sidebar";
import { ChatContainer } from "../components/chat/ChatContainer";

export default function Home() {
  const [threadId, setThreadId] = useState("");

  useEffect(() => {
    setThreadId(crypto.randomUUID());
  }, []);

  return (
    <div className="flex h-screen">
      <Sidebar threadId={threadId} />
      <main className="flex flex-1 flex-col">
        <ChatContainer />
      </main>
    </div>
  );
}
