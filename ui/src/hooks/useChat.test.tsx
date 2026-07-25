import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const { deleteConversation } = vi.hoisted(() => ({
  deleteConversation: vi.fn().mockResolvedValue(undefined),
}));

vi.mock("../lib/api", () => ({
  deleteConversation,
  queryStream: vi.fn(),
}));

import { useChat } from "./useChat";

describe("useChat", () => {
  it("changes the local thread and deletes the previous remote conversation", async () => {
    const onThreadChange = vi.fn();
    const { result } = renderHook(() => useChat({ threadId: "old-thread", onThreadChange }));

    await act(async () => {
      await result.current.clearHistory();
    });

    expect(deleteConversation).toHaveBeenCalledWith("old-thread");
    expect(onThreadChange).toHaveBeenCalledOnce();
    expect(onThreadChange.mock.calls[0][0]).not.toBe("old-thread");
    expect(result.current.messages).toEqual([]);
  });
});
