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
