import { describe, expect, it, vi } from "vitest";

import { deleteConversation, queryStream } from "./api";

function sseResponse(chunks: string[]): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
  return new Response(stream, { status: 200 });
}

describe("RAG API client", () => {
  it("parses SSE events split across network chunks", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        sseResponse([
          'event: token\ndata: {"content":"hel',
          'lo"}\n\nevent: source\ndata: {"chunks":["[S1] SOURCE: guide.md"]}\n\n',
        ]),
      ),
    );

    const events = [];
    for await (const event of queryStream({ q: "hello", thread_id: "thread-1" })) events.push(event);

    expect(events).toEqual([
      { event: "token", data: { content: "hello" } },
      { event: "source", data: { chunks: ["[S1] SOURCE: guide.md"] } },
    ]);
  });

  it("deletes a conversation through the same-origin proxy", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);

    await deleteConversation("thread id/1");

    expect(fetchMock).toHaveBeenCalledWith("/api/rag/conversations/thread%20id%2F1", {
      method: "DELETE",
      signal: undefined,
    });
  });
});
