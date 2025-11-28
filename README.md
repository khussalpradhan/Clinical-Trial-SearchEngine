Install python 3.11.9

python -m venv .venv 

source .venv/bin/activate

pip install -r backend/requirements.txt     

Then do :

docker-compose up -d
Initialise psql
python -m backend.db.init_db

Scrape data
python -m backend.db.scrape_clinical_trials --max-studies 600000

Initialise opensearch index
python -m backend.search.init_index

Index psql data into opensearch
python -m backend.search.reindex_from_postgres --chunk-size 1000

Creating embeddings
python -m backend.search.build_faiss_index