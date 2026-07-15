import { config } from "./config";
import type { HealthResponse, QueryRequest, QueryResponse } from "./types";

class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function headers(): Record<string, string> {
  const h: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (config.apiKey) {
    h["Authorization"] = `Bearer ${config.apiKey}`;
  }
  return h;
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new ApiError(res.status, body || res.statusText);
  }
  return res.json();
}

export async function query(body: QueryRequest, signal?: AbortSignal): Promise<QueryResponse> {
  const res = await fetch(`${config.apiBaseUrl}/query`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(body),
    signal,
  });
  return handleResponse<QueryResponse>(res);
}

export type SSEEvent =
  | { event: "thought"; data: { content: string } }
  | { event: "token"; data: { content: string } }
  | { event: "source"; data: { chunks: string[] } }
  | { event: "error"; data: { message: string } }
  | { event: "done"; data: { sources_used: string[] } };

export async function* queryStream(
  body: QueryRequest,
  signal?: AbortSignal,
): AsyncGenerator<SSEEvent> {
  const h: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (config.apiKey) {
    h["Authorization"] = `Bearer ${config.apiKey}`;
  }

  const res = await fetch(`${config.apiBaseUrl}/query/stream`, {
    method: "POST",
    headers: h,
    body: JSON.stringify(body),
    signal,
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new ApiError(res.status, text || res.statusText);
  }

  const reader = res.body?.getReader();
  if (!reader) throw new Error("Streaming not supported by the browser.");

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    let currentEvent = "";

    for (const line of lines) {
      const trimmed = line.trim();

      if (trimmed.startsWith("event: ")) {
        currentEvent = trimmed.slice(7).trim();
      } else if (trimmed.startsWith("data: ")) {
        const raw = trimmed.slice(6);
        try {
          const parsed = JSON.parse(raw);
          yield { event: currentEvent as SSEEvent["event"], data: parsed } as SSEEvent;
        } catch {
          // skip malformed data
        }
        currentEvent = "";
      }
    }
  }
}

export async function healthCheck(signal?: AbortSignal): Promise<HealthResponse> {
  const res = await fetch(`${config.apiBaseUrl}/health`, { signal });
  return handleResponse<HealthResponse>(res);
}

export interface IngestResponse {
  status: string;
  message: string;
}

export async function uploadDocument(
  file: File,
  sourceType = "upload",
  signal?: AbortSignal,
): Promise<IngestResponse> {
  const form = new FormData();
  form.append("file", file);
  form.append("source_type", sourceType);

  const h: Record<string, string> = {};
  if (config.apiKey) {
    h["Authorization"] = `Bearer ${config.apiKey}`;
  }

  const res = await fetch(`${config.apiBaseUrl}/ingest/document`, {
    method: "POST",
    headers: h,
    body: form,
    signal,
  });
  return handleResponse<IngestResponse>(res);
}
