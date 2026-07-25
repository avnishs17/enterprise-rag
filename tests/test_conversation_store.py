import json
from unittest.mock import MagicMock, patch

import pytest

from app.services import conversation

pytestmark = pytest.mark.unit


def test_history_discards_invalid_redis_entries():
    redis = MagicMock()
    redis.lrange.return_value = [
        json.dumps({"role": "user", "content": "valid"}),
        json.dumps({"role": "system", "content": "ignored"}),
        json.dumps({"role": "assistant", "content": 42}),
    ]
    with patch.object(conversation, "_get_client", return_value=redis):
        result = conversation.get_recent_messages("thread-1")

    assert result == [{"role": "user", "content": "valid"}]
    redis.lrange.assert_called_once_with("rag:conversation:thread-1", -conversation.settings.MAX_CONVERSATION_MESSAGES, -1)


def test_append_exchange_trims_and_sets_ttl():
    redis = MagicMock()
    pipeline = MagicMock()
    pipeline.__enter__.return_value = pipeline
    redis.pipeline.return_value = pipeline

    with patch.object(conversation, "_get_client", return_value=redis):
        conversation.append_exchange("thread-1", "question", "answer")

    pipeline.rpush.assert_called_once()
    entries = pipeline.rpush.call_args.args[1:]
    assert [json.loads(entry) for entry in entries] == [
        {"role": "user", "content": "question"},
        {"role": "assistant", "content": "answer"},
    ]
    pipeline.ltrim.assert_called_once()
    pipeline.expire.assert_called_once_with("rag:conversation:thread-1", conversation.settings.CONVERSATION_HISTORY_TTL_SECONDS)
    pipeline.execute.assert_called_once()


def test_delete_history_is_best_effort():
    redis = MagicMock()
    with patch.object(conversation, "_get_client", return_value=redis):
        conversation.delete_history("thread-1")
    redis.delete.assert_called_once_with("rag:conversation:thread-1")
