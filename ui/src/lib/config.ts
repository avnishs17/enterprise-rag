// Browser requests stay same-origin. The Next.js route handler owns the
// server-only backend URL and bearer token, so no backend credential is put in
// NEXT_PUBLIC_* or shipped in the JavaScript bundle.
export const config = {
  apiBaseUrl: "/api/rag",
  appName: "Enterprise Agentic RAG",
} as const;
