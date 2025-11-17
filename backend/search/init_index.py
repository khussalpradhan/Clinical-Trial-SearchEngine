# backend/search/init_index.py
import json
import pathlib
from opensearchpy import OpenSearch
from backend.config import OPENSEARCH_HOST, TRIALS_INDEX_NAME

def create_index():
    client = OpenSearch(
        hosts=[OPENSEARCH_HOST],
        http_compress=True
    )

    if client.indices.exists(index=TRIALS_INDEX_NAME):
        print(f"Index '{TRIALS_INDEX_NAME}' already exists.")
        return

    mapping_path = pathlib.Path(__file__).parent / "mapping.json"
    body = json.loads(mapping_path.read_text())

    client.indices.create(index=TRIALS_INDEX_NAME, body=body)
    print(f"✅ Created index '{TRIALS_INDEX_NAME}'.")

if __name__ == "__main__":
    create_index()
