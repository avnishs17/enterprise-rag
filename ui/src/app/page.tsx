"use client";

import { useState } from "react";
import { Sidebar } from "../components/layout/Sidebar";
import { ChatContainer } from "../components/chat/ChatContainer";

function generateId(): string {
  return crypto.randomUUID();
}

export default function Home() {
  const [threadId] = useState(generateId);

  return (
    <div className="flex h-screen">
      <Sidebar threadId={threadId} />
      <main className="flex flex-1 flex-col">
        <ChatContainer />
      </main>
    </div>
  );
}
