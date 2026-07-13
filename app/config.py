import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Settings:

    PROCESSED_DATA_DIR = "processed_data"

    # Logfire Observability
    LOGFIRE_TOKEN = os.getenv("LOGFIRE_TOKEN")
    LOGFIRE_PROJECT = os.getenv("LOGFIRE_PROJECT")
    LOGFIRE_BASE_URL = os.getenv("LOGFIRE_BASE_URL")


    # Embedding model configuration
    BATCH_SIZE = 64
    EMBEDDING_DIM = 1024

    JINA_API_KEY = os.getenv("JINA_API_KEY")
    JINA_EMBEDDING_URL = os.getenv("JINA_EMBEDDING_URL")
    JINA_MODEL = os.getenv("JINA_MODEL")
    FALLBACK_MODEL = os.getenv("FALLBACK_MODEL")

    # --- VECTOR DB (QDRANT) ---
    QDRANT_URL = os.getenv("QDRANT_CLUSTER_ENDPOINT")
    QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
    QDRANT_COLLECTION = "enterprise_rag"

    # --- REASONING ENGINE (GROQ) ---
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    GROQ_MODEL = os.getenv("GROQ_MODEL")
    GROQ_MODEL_B = os.getenv("GROQ_MODEL_B")
    GROQ_FALLBACK_API_KEY = os.getenv("GROQ_FALLBACK_API_KEY")

    # --- LLM GATEWAY (PORTKEY) ---
    PORTKEY_API_KEY = os.getenv("PORTKEY_API_KEY")
    GROQ_SLUG =  f"rag/{GROQ_MODEL}"     # primary: @rag/llama-3.3-70b-versatile
    GROQ_SLUG_2 = f"brag/{GROQ_MODEL_B}"  # fallback: @brag/llama-3.1-8b-instant


    # --- OBSERVABILITY ---
    LANGSMITH_TRACING = os.getenv("LANGSMITH_TRACING", "true")
    LANGSMITH_API_KEY = os.getenv("LANGSMITH_API_KEY")
    LANGSMITH_PROJECT = os.getenv("LANGSMITH_PROJECT", "enterprise-rag")
    LANGSMITH_ENDPOINT = os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")

# Apply LangChain environment variables for automatic tracing
os.environ["LANGCHAIN_TRACING_V2"] = os.getenv("LANGSMITH_TRACING", "true")
os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGSMITH_API_KEY", "")
os.environ["LANGCHAIN_PROJECT"] = os.getenv("LANGSMITH_PROJECT", "rag_scale_test")
os.environ["LANGCHAIN_ENDPOINT"] = os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")

settings = Settings()
