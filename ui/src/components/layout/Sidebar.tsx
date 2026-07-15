"use client";

import { useState, useEffect } from "react";
import { Brain, Activity, Hash } from "lucide-react";
import { healthCheck } from "../../lib/api";
import { cn } from "../../lib/utils";
import { UploadPanel } from "../upload/UploadPanel";

interface SidebarProps {
  threadId: string;
}

type HealthStatus = "checking" | "connected" | "disconnected";

export function Sidebar({ threadId }: SidebarProps) {
  const [backendStatus, setBackendStatus] = useState<HealthStatus>("checking");

  useEffect(() => {
    let cancelled = false;

    async function check() {
      try {
        await healthCheck();
        if (!cancelled) setBackendStatus("connected");
      } catch {
        if (!cancelled) setBackendStatus("disconnected");
      }
    }

    check();
    const interval = setInterval(check, 30_000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  const statusColor =
    backendStatus === "connected"
      ? "text-green-400"
      : backendStatus === "disconnected"
        ? "text-red-400"
        : "text-yellow-400";

  return (
    <aside className="flex h-full w-60 flex-col border-r border-zinc-800 bg-zinc-900/50">
      <div className="p-4 pb-0">
        <div className="mb-4 flex items-center gap-2">
          <Brain className="h-6 w-6 text-blue-500" />
          <span className="text-sm font-semibold text-zinc-100">Agent OS</span>
        </div>

        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-2 rounded-lg bg-zinc-800/50 px-3 py-2">
            <Activity className={cn("h-4 w-4", statusColor)} />
            <span className="text-xs text-zinc-400">Backend</span>
            <span className={cn("ml-auto text-xs capitalize", statusColor)}>
              {backendStatus}
            </span>
          </div>

          <div className="flex items-center gap-2 rounded-lg bg-zinc-800/50 px-3 py-2">
            <Hash className="h-4 w-4 text-zinc-500" />
            <span className="text-xs text-zinc-400">Memory</span>
            <span className="ml-auto text-xs text-zinc-500">
              {threadId.slice(0, 8)}
            </span>
          </div>
        </div>
      </div>

      <UploadPanel />

      <div className="mt-auto p-4 pt-0">
        <p className="text-center text-[10px] text-zinc-600">
          Enterprise Agentic RAG
        </p>
      </div>
    </aside>
  );
}
