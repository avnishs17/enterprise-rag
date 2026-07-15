import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Enterprise Agentic RAG",
  description: "Enterprise Agentic RAG with LangGraph, Guardrails, and LLM Gateway",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="scrollbar-thin">{children}</body>
    </html>
  );
}
