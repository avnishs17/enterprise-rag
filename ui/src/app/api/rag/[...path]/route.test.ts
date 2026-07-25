import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DELETE, POST } from "./route";

describe("RAG proxy route", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("rejects paths outside the explicit backend allowlist", async () => {
    const response = await POST(
      new NextRequest("http://localhost:3000/api/rag/admin"),
      { params: Promise.resolve({ path: ["admin"] }) },
    );

    expect(response.status).toBe(404);
    expect(await response.json()).toEqual({ detail: "Not found" });
  });

  it("forwards conversation deletion with the server-only API key", async () => {
    vi.stubEnv("RAG_API_URL", "http://backend.internal:8000");
    vi.stubEnv("RAG_API_KEY", "server-secret");
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);

    const response = await DELETE(
      new NextRequest("http://localhost:3000/api/rag/conversations/thread-1", { method: "DELETE" }),
      { params: Promise.resolve({ path: ["conversations", "thread-1"] }) },
    );

    expect(response.status).toBe(204);
    expect(fetchMock).toHaveBeenCalledWith(
      new URL("conversations/thread-1", "http://backend.internal:8000/"),
      expect.objectContaining({ method: "DELETE", cache: "no-store" }),
    );
    expect(fetchMock.mock.calls[0][1].headers.get("authorization")).toBe("Bearer server-secret");
  });
});
