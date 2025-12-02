#!/usr/bin/env python3
"""Quick script to add parsed_criteria column"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import psycopg2
from config import POSTGRES_DSN

conn = psycopg2.connect(POSTGRES_DSN)
cur = conn.cursor()

# Add column
print("Adding parsed_criteria column...")
cur.execute("ALTER TABLE trials ADD COLUMN IF NOT EXISTS parsed_criteria JSONB;")
cur.execute("CREATE INDEX IF NOT EXISTS idx_trials_parsed_criteria ON trials USING GIN (parsed_criteria);")
conn.commit()

print("Column added successfully!")
cur.close()
conn.close()
