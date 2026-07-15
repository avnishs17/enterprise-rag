function getEnv(name: string, fallback: string): string {
  if (typeof process !== "undefined" && process.env?.[name]) {
    return process.env[name]!;
  }
  return fallback;
}

export const config = {
  get apiBaseUrl(): string {
    return getEnv("NEXT_PUBLIC_API_URL", "http://localhost:8000");
  },

  get apiKey(): string {
    return getEnv("NEXT_PUBLIC_API_KEY", "");
  },

  get appName(): string {
    return "Enterprise Agentic RAG";
  },
} as const;
