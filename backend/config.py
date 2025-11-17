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
