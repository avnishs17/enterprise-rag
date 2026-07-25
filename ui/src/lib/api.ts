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

function jsonHeaders(): Record<string, string> {
  return { "Content-Type": "application/json" };
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
    headers: jsonHeaders(),
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

function parseSseBlock(block: string): SSEEvent | null {
  let event = "";
  const data: string[] = [];
  for (const line of block.split(/\r?\n/)) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
  }
  if (!event || data.length === 0) return null;
  try {
    return { event: event as SSEEvent["event"], data: JSON.parse(data.join("\n")) } as SSEEvent;
  } catch {
    return null;
  }
}

export async function* queryStream(
  body: QueryRequest,
  signal?: AbortSignal,
): AsyncGenerator<SSEEvent> {
  const res = await fetch(`${config.apiBaseUrl}/query/stream`, {
    method: "POST",
    headers: jsonHeaders(),
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
  const consumeBlocks = function* (): Generator<SSEEvent> {
    const normalized = buffer.replace(/\r\n/g, "\n");
    const blocks = normalized.split("\n\n");
    buffer = blocks.pop() ?? "";
    for (const block of blocks) {
      const event = parseSseBlock(block);
      if (event) yield event;
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    yield* consumeBlocks();
  }

  buffer += decoder.decode();
  yield* consumeBlocks();
}

export async function healthCheck(signal?: AbortSignal): Promise<HealthResponse> {
  const res = await fetch(`${config.apiBaseUrl}/health`, { signal });
  return handleResponse<HealthResponse>(res);
}

export interface IngestResponse {
  job_id: string;
  status: "queued" | "processing" | "completed" | "failed";
  progress: number;
  message: string;
}

export async function uploadDocument(
  file: File,
  signal?: AbortSignal,
): Promise<IngestResponse> {
  const form = new FormData();
  form.append("file", file);

  const res = await fetch(`${config.apiBaseUrl}/ingest/document`, {
    method: "POST",
    body: form,
    signal,
  });
  return handleResponse<IngestResponse>(res);
}

export async function deleteConversation(threadId: string, signal?: AbortSignal): Promise<void> {
  const res = await fetch(`${config.apiBaseUrl}/conversations/${encodeURIComponent(threadId)}`, {
    method: "DELETE",
    signal,
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new ApiError(res.status, body || res.statusText);
  }
}

export async function getIngestionStatus(jobId: string, signal?: AbortSignal): Promise<IngestResponse> {
  const res = await fetch(`${config.apiBaseUrl}/ingest/document/${jobId}`, { signal });
  return handleResponse<IngestResponse>(res);
}
