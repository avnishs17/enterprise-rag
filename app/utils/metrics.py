from prometheus_client import Counter, Gauge, Histogram

RAG_REQUESTS_TOTAL = Counter(
    "rag_requests_total",
    "Total number of /query requests",
    ["status"],
)

RAG_REQUEST_DURATION = Histogram(
    "rag_request_duration_seconds",
    "Latency of /query requests in seconds",
)

GUARDRAILS_BLOCKS_TOTAL = Counter(
    "guardrails_blocks_total",
    "Number of requests blocked or allowed by guardrails",
    ["blocked"],
)

RAG_PIPELINE_STAGE_DURATION = Histogram(
    "rag_pipeline_stage_duration_seconds",
    "Duration of each RAG pipeline stage",
    ["stage"],
)

RAG_STREAM_TIME_TO_FIRST_TOKEN = Histogram(
    "rag_stream_time_to_first_token_seconds",
    "Time from request start until the first response token is emitted",
    ["response_type"],
)

RAG_STREAM_OUTPUT_CHARACTERS_TOTAL = Counter(
    "rag_stream_output_characters_total",
    "Characters emitted through streaming responses",
)

RAG_ACTIVE_STREAMS = Gauge(
    "rag_active_streams",
    "Currently active SSE response streams",
)

LLM_FALLBACKS_TOTAL = Counter(
    "llm_fallbacks_total",
    "LLM requests rerouted from the primary provider to a fallback",
    ["mode"],
)
