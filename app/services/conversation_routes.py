"""Conversation deletion endpoint."""

import asyncio
from typing import Annotated

import logfire
from fastapi import APIRouter, Depends, Path, status
from fastapi.responses import Response

from app.services.conversation import delete_history
from app.services.memory import delete_memories, is_enabled as mem0_enabled
from app.utils.security import verify_api_key

router = APIRouter(prefix="/conversations", tags=["conversations"])
ThreadId = Annotated[str, Path(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")]


@router.delete("/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(thread_id: ThreadId, _api_key: str | None = Depends(verify_api_key)):
    """Permanently clear the exact history and Mem0 scope for one thread."""
    await asyncio.to_thread(delete_history, thread_id)
    if mem0_enabled():
        await asyncio.to_thread(delete_memories, thread_id)
    logfire.info("Conversation deleted.", thread_id=thread_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
