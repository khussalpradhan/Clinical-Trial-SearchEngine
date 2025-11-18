# backend/db/init_db.py
import pathlib
import psycopg2
from backend.config import POSTGRES_DSN

def run_schema():
    schema_path = pathlib.Path(__file__).parent / "schema.sql"
    sql = schema_path.read_text()

    conn = psycopg2.connect(POSTGRES_DSN)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql)
        print("✅ Postgres schema applied successfully.")
    finally:
        conn.close()

if __name__ == "__main__":
    run_schema()
