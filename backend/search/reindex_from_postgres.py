# backend/search/reindex_from_postgres.py

import argparse
from typing import Any, Dict, Generator, List, Tuple

import psycopg2
import psycopg2.extras
from opensearchpy import OpenSearch, helpers

from backend.config import POSTGRES_DSN, OPENSEARCH_HOST, TRIALS_INDEX_NAME


def get_db_connection():
    return psycopg2.connect(POSTGRES_DSN)


def get_opensearch_client():
    return OpenSearch(
        hosts=[OPENSEARCH_HOST],
        http_compress=True,
    )


def fetch_trials_stream(conn) -> psycopg2.extras.RealDictCursor:
    """
    Use a server-side named cursor so we don't load all 550k rows into memory.
    """
    cur = conn.cursor(name="trials_stream_cursor",
                      cursor_factory=psycopg2.extras.RealDictCursor)
    # how many rows to fetch each network round-trip
    cur.itersize = 1000

    cur.execute(
        """
        SELECT
            id,
            nct_id,
            brief_title,
            official_title,
            brief_summary,
            detailed_description,
            study_type,
            phase,
            overall_status,
            conditions,
            conditions_cuis,
            interventions,
            start_date,
            primary_completion_date,
            completion_date,
            last_updated,
            eligibility_criteria_raw,
            min_age_years,
            max_age_years,
            sex,
            healthy_volunteers,
            enrollment_target
        FROM trials
        ORDER BY id;
        """
    )
    return cur


def fetch_sites_for_trial(conn, trial_id: int) -> List[Dict[str, Any]]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                facility_name,
                city,
                state,
                country,
                zip,
                recruitment_status
            FROM sites
            WHERE trial_id = %s;
            """,
            (trial_id,),
        )
        return list(cur.fetchall())


def fetch_criteria_for_trial(conn, trial_id: int) -> Tuple[List[str], List[str]]:
    inclusion: List[str] = []
    exclusion: List[str] = []

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT type, text
            FROM criteria
            WHERE trial_id = %s
            ORDER BY sequence_no;
            """,
            (trial_id,),
        )
        for row in cur:
            t = row["type"]
            text = row["text"] or ""
            if t == "inclusion":
                inclusion.append(text)
            elif t == "exclusion":
                exclusion.append(text)

    return inclusion, exclusion


def build_doc(
    trial_row: Dict[str, Any],
    sites: List[Dict[str, Any]],
    incl: List[str],
    excl: List[str],
) -> Dict[str, Any]:
    """
    Map Postgres trial + sites + criteria into an OpenSearch document
    that matches mapping.json.
    """
    title = trial_row.get("brief_title") or trial_row.get("official_title")

    locations = []
    for s in sites:
        locations.append(
            {
                "facility_name": s.get("facility_name"),
                "city": s.get("city"),
                "state": s.get("state"),
                "country": s.get("country"),
            }
        )

    #inclusion-only text from eligibility_criteria_raw using regex logic from FAISS
    import re
    raw_text = trial_row.get("eligibility_criteria_raw") or ""
    inclusion_text = raw_text
    if raw_text:
        match = re.search(r'(?i)exclusion\s+criteria\s*:?', raw_text)
        if match:
            inclusion_text = raw_text[:match.start()].strip()
        incl_match = re.search(r'(?i)inclusion\s+criteria\s*:?([\s\S]*?)(?=exclusion\s+criteria|$)', raw_text)
        if incl_match:
            inclusion_text = incl_match.group(1).strip()
        if inclusion_text:
            inclusion_text = inclusion_text[:1000]
    else:
        inclusion_text = None

    doc = {
        "id": trial_row["id"],
        "nct_id": trial_row["nct_id"],
        "title": title,
        "brief_summary": trial_row.get("brief_summary"),
        "detailed_description": trial_row.get("detailed_description"),
        "conditions": trial_row.get("conditions") or [],
        "conditions_cuis": trial_row.get("conditions_cuis") or [],
        "conditions_all": " ".join(trial_row.get("conditions") or []),
        "interventions": trial_row.get("interventions") or [],
        "study_type": trial_row.get("study_type"),
        "phase": trial_row.get("phase"),
        "overall_status": trial_row.get("overall_status"),
        "start_date": trial_row.get("start_date"),
        "primary_completion_date": trial_row.get("primary_completion_date"),
        "completion_date": trial_row.get("completion_date"),
        "last_updated": trial_row.get("last_updated"),
        "locations": locations,
        "criteria_inclusion": " ".join(incl) if incl else None,
        "criteria_exclusion": " ".join(excl) if excl else None,
        "criteria_inclusion_clean": inclusion_text,
        "eligibility_criteria_raw": trial_row.get("eligibility_criteria_raw"),
        "min_age_years": trial_row.get("min_age_years"),
        "max_age_years": trial_row.get("max_age_years"),
        "sex": trial_row.get("sex"),
        "healthy_volunteers": trial_row.get("healthy_volunteers"),
        "enrollment": trial_row.get("enrollment_target")
    }
    return doc


def generate_actions(conn) -> Generator[Dict[str, Any], None, None]:
    """
    Stream docs from Postgres and yield bulk indexing actions.
    """
    trials_cursor = fetch_trials_stream(conn)

    count = 0
    for trial in trials_cursor:
        trial_id = trial["id"]
        sites = fetch_sites_for_trial(conn, trial_id)
        incl, excl = fetch_criteria_for_trial(conn, trial_id)
        doc = build_doc(trial, sites, incl, excl)

        count += 1
        if count % 10_000 == 0:
            print(f"Prepared {count} documents so far...")

        yield {
            "_index": TRIALS_INDEX_NAME,
            "_id": trial["nct_id"],   # stable id
            "_source": doc,
        }


def reindex(chunk_size: int = 1000, refresh: bool = True):
    conn = get_db_connection()
    client = get_opensearch_client()

    try:
        print(f"Starting reindex into '{TRIALS_INDEX_NAME}'")

        # Speed up bulk indexing: disable refresh for the index during bulk
        print("Setting refresh_interval = -1 for bulk indexing...")
        client.indices.put_settings(
            index=TRIALS_INDEX_NAME,
            body={"index": {"refresh_interval": "-1"}}
        )

        success, errors = helpers.bulk(
            client,
            generate_actions(conn),
            chunk_size=chunk_size,
            request_timeout=300,
        )

        print(f"Reindex complete. Successfully indexed: {success}")
        if errors:
            print("⚠ Some errors occurred during bulk indexing:")
            print(errors)

        if refresh:
            print("Restoring refresh_interval to 1s and refreshing index...")
            client.indices.put_settings(
                index=TRIALS_INDEX_NAME,
                body={"index": {"refresh_interval": "1s"}}
            )
            client.indices.refresh(index=TRIALS_INDEX_NAME)
            print("Index refresh done.")

    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Reindex all trials from Postgres into OpenSearch."
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=1000,
        help="Bulk chunk size (number of docs per bulk request).",
    )
    parser.add_argument(
        "--no-refresh",
        action="store_true",
        help="Skip final index refresh and refresh_interval reset.",
    )
    args = parser.parse_args()

    reindex(chunk_size=args.chunk_size, refresh=not args.no_refresh)


if __name__ == "__main__":
    main()
