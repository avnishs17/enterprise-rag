import { NextRequest, NextResponse } from "next/server";

const ALLOWED_PATHS = new Set(["health", "query", "query/stream", "ingest/document"]);
const JOB_PATH = /^ingest\/document\/[0-9a-f-]{36}$/i;
const CONVERSATION_PATH = /^conversations\/[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/;

function backendUrl(path: string): URL | null {
  const baseUrl = process.env.RAG_API_URL;
  if (!baseUrl) return null;
  return new URL(path, `${baseUrl.replace(/\/$/, "")}/`);
}

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path: parts } = await context.params;
  const path = parts.join("/");
  if (!ALLOWED_PATHS.has(path) && !JOB_PATH.test(path) && !CONVERSATION_PATH.test(path)) {
    return NextResponse.json({ detail: "Not found" }, { status: 404 });
  }

  const url = backendUrl(path);
  if (!url) {
    console.error("RAG_API_URL is not configured");
    return NextResponse.json({ detail: "RAG service is unavailable" }, { status: 503 });
  }

  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);
  if (process.env.RAG_API_KEY) headers.set("authorization", `Bearer ${process.env.RAG_API_KEY}`);

  let upstream: Response;
  try {
    upstream = await fetch(url, {
      method: request.method,
      headers,
      body: request.method === "GET" || request.method === "HEAD" ? undefined : await request.arrayBuffer(),
      cache: "no-store",
    });
  } catch {
    return NextResponse.json({ detail: "RAG service is unavailable" }, { status: 503 });
  }

  const responseHeaders = new Headers();
  for (const header of ["content-type", "cache-control", "x-accel-buffering"]) {
    const value = upstream.headers.get(header);
    if (value) responseHeaders.set(header, value);
  }
  return new NextResponse(upstream.body, { status: upstream.status, headers: responseHeaders });
}

export const GET = proxy;
export const POST = proxy;
export const DELETE = proxy;
