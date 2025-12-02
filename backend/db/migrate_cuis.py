import psycopg2
import psycopg2.extras
from backend.config import POSTGRES_DSN
from backend.nlp.umls_linker import UMLSLinker
import time

def migrate():
    print("Connecting to database...")
    conn = psycopg2.connect(POSTGRES_DSN)
    conn.autocommit = False # We will manage commits manually
    
    print("Loading UMLS Linker (this may take a moment)...")
    linker = UMLSLinker()
    
    try:
        updated_total = 0
        start_time = time.time()
        
        while True:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # Fetch a batch of unprocessed trials
                # We use LIMIT to keep memory low
                cur.execute("""
                    SELECT nct_id, conditions 
                    FROM trials 
                    WHERE conditions IS NOT NULL 
                      AND cardinality(conditions) > 0 
                      AND conditions_cuis IS NULL 
                    LIMIT 1000
                """)
                rows = cur.fetchall()
                
                if not rows:
                    print("No more trials to process. Migration complete!")
                    break
                
                print(f"Processing batch of {len(rows)} trials...")
                
                # Process batch
                for row in rows:
                    nct_id = row['nct_id']
                    conditions = row['conditions']
                    
                    # Extract CUIs
                    cuis = set()
                    for cond in conditions:
                        extracted = linker.extract_cuis(cond)
                        cuis.update(extracted)
                    
                    # Update DB
                    cui_list = list(cuis)
                    cur.execute(
                        "UPDATE trials SET conditions_cuis = %s WHERE nct_id = %s",
                        (cui_list, nct_id)
                    )
                
                # Commit after each batch
                conn.commit()
                updated_total += len(rows)
                
                elapsed = time.time() - start_time
                rate = updated_total / elapsed
                print(f"Total Processed: {updated_total} - Rate: {rate:.1f} trials/sec")
                
    except Exception as e:
        conn.rollback()
        print(f"Error: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
