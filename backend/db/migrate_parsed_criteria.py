#!/usr/bin/env python3
"""
Migration script to populate parsed_criteria JSONB column for all trials.

This script:
1. Loads the CriteriaParser
2. Fetches trials in batches where parsed_criteria IS NULL
3. Parses eligibility_criteria_raw 
4. Stores result as JSONB in parsed_criteria column
5. Commits in batches for memory efficiency and resume capability
"""

import sys
import json
import logging
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor, Json

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import POSTGRES_DSN
from nlp.criteria_parser import CriteriaParser

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def migrate():
    """Populate parsed_criteria for all trials in batches."""
    logger.info("Starting parsed_criteria migration...")
    
    # Initialize parser
    logger.info("Loading CriteriaParser...")
    parser = CriteriaParser()
    logger.info("CriteriaParser loaded successfully.")
    
    # Connect to database
    conn = psycopg2.connect(POSTGRES_DSN)
    conn.autocommit = False
    
    try:
        processed_count = 0
        batch_num = 0
        
        while True:
            batch_num += 1
            logger.info(f"Processing batch {batch_num}...")
            
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Fetch next batch of trials without cached criteria
                cur.execute("""
                    SELECT id, nct_id, 
                           eligibility_criteria_raw,
                           min_age_years,
                           max_age_years,
                           sex,
                           conditions,
                           conditions_cuis
                    FROM trials
                    WHERE parsed_criteria IS NULL
                    LIMIT 1000
                """)
                
                batch = cur.fetchall()
                
                if not batch:
                    logger.info("No more trials to process.")
                    break
                
                logger.info(f"Batch {batch_num}: Processing {len(batch)} trials...")
                
                # Process each trial in batch
                for row in batch:
                    trial_id = row['id']
                    nct_id = row['nct_id']
                    criteria_text = row['eligibility_criteria_raw']
                    
                    # Parse criteria AND merge with DB metadata
                    if criteria_text:
                        try:
                            # 1. Parse text
                            parsed_data = parser.parse(criteria_text)
                            
                            # 2. Override with DB metadata (same as feasibility_scorer.py)
                            if row['min_age_years'] is not None:
                                parsed_data['age_range'][0] = float(row['min_age_years'])
                            if row['max_age_years'] is not None:
                                parsed_data['age_range'][1] = float(row['max_age_years'])
                            
                            # Gender
                            if row['sex']:
                                if row['sex'].upper() == "MALE":
                                    parsed_data['gender'] = "Male"
                                elif row['sex'].upper() == "FEMALE":
                                    parsed_data['gender'] = "Female"
                                else:
                                    parsed_data['gender'] = "All"
                            
                            # Conditions from DB (merge with parsed)
                            db_conditions = row['conditions'] or []
                            parsed_conditions = set(parsed_data.get('conditions', []))
                            all_conditions = parsed_conditions.union(set(db_conditions))
                            parsed_data['conditions'] = list(all_conditions)
                            
                            # Store conditions_cuis separately (not parsed, from DB)
                            parsed_data['conditions_cuis'] = row['conditions_cuis'] or []
                            
                            # Update database with JSONB
                            cur.execute("""
                                UPDATE trials
                                SET parsed_criteria = %s
                                WHERE id = %s
                            """, (Json(parsed_data), trial_id))
                            
                            processed_count += 1
                            
                            if processed_count % 100 == 0:
                                logger.info(f"  Processed {processed_count} trials so far...")
                        
                        except Exception as e:
                            logger.error(f"  Error parsing trial {nct_id}: {e}")
                            # Set to empty dict on error so we don't retry forever
                            cur.execute("""
                                UPDATE trials
                                SET parsed_criteria = %s
                                WHERE id = %s
                            """, (Json({}), trial_id))
                    else:
                        # No criteria text - store empty dict
                        cur.execute("""
                            UPDATE trials
                            SET parsed_criteria = %s
                            WHERE id = %s
                        """, (Json({}), trial_id))
                        processed_count += 1
                
                # Commit batch
                conn.commit()
                logger.info(f"Batch {batch_num} committed ({len(batch)} trials).")
        
        logger.info(f"Migration complete! Processed {processed_count} trials in {batch_num} batches.")
    
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        conn.rollback()
        raise
    
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
