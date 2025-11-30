# backend/config.py
import os
from dotenv import load_dotenv

# This will load .env from the project root when you run from there
load_dotenv()

POSTGRES_DSN = os.getenv(
    "POSTGRES_DSN",
    "postgresql://clinical_user:clinical_pass@localhost:5432/clinical_trials",
)

OPENSEARCH_HOST = os.getenv("OPENSEARCH_HOST", "http://localhost:9200")
TRIALS_INDEX_NAME = os.getenv("TRIALS_INDEX_NAME", "trials_v1")


EMBEDDING_MODEL_NAME = os.getenv(
    "EMBEDDING_MODEL_NAME", "pritamdeka/S-PubMedBert-MS-MARCO"
)
EMBEDDINGS_DIR = os.getenv("EMBEDDINGS_DIR", "data")
FAISS_INDEX_PATH = os.getenv(
    "FAISS_INDEX_PATH", os.path.join(EMBEDDINGS_DIR, "trials_faiss.index")
)
FAISS_META_PATH = os.getenv(
    "FAISS_META_PATH", os.path.join(EMBEDDINGS_DIR, "trials_faiss_meta.json")
)