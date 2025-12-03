import argparse
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
import psycopg2.extras
import requests
from psycopg2.extras import Json
import time
from psycopg2.extras import Json, RealDictCursor

from backend.config import POSTGRES_DSN

# Don't initialize UMLS at import time - too memory intensive
# It will be initialized on first use in normalize_study()
UMLS = None

def get_umls():
    global UMLS
    if UMLS is None:
        try:
            from backend.nlp.umls_linker import UMLSLinker
            UMLS = UMLSLinker()
            print("UMLS Linker loaded successfully")
        except Exception as e:
            print(f"Warning: Could not load UMLSLinker: {e}")
            UMLS = False  # Mark as failed, don't retry
    return UMLS if UMLS is not False else None

JOB_NAME = "studies_full"
API_BASE = "https://clinicaltrials.gov/api/v2/studies"

def get_or_create_ingestion_state(conn):
    """
    Ensure there is a row in ingestion_state for this job and return it.
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT id, job_name, page_token, processed_count, last_run_at
            FROM ingestion_state
            WHERE job_name = %s;
            """,
            (JOB_NAME,),
        )
        row = cur.fetchone()
        if row:
            return row

        # create new state row
        cur.execute(
            """
            INSERT INTO ingestion_state (job_name, page_token, processed_count, last_run_at)
            VALUES (%s, NULL, 0, NOW())
            RETURNING id, job_name, page_token, processed_count, last_run_at;
            """,
            (JOB_NAME,),
        )
        return cur.fetchone()


def update_ingestion_state(conn, page_token, processed_delta):
    """
    Update page_token and increment processed_count by processed_delta.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE ingestion_state
            SET page_token = %s,
                processed_count = processed_count + %s,
                last_run_at = NOW()
            WHERE job_name = %s;
            """,
            (page_token, processed_delta, JOB_NAME),
        )

def parse_iso_date(date_struct: Optional[Dict[str, Any]]) -> Optional[datetime]:
    """
    ClinicalTrials v2 date struct looks like:
    { "date": "2024-01-01", "type": "ACTUAL" }
    We just care about the ISO date string.
    """
    if not date_struct:
        return None
    date_str = date_struct.get("date")
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str)
    except Exception:
        return None


def parse_age_to_years(age_str: Optional[str]) -> Optional[int]:
    """
    Convert things like '18 Years', '6 Months', '3 Weeks', 'N/A' to integer years.
    Very rough but good enough for filtering.
    """
    if not age_str:
        return None

    s = age_str.strip().lower()
    if s in {"n/a", "none", "not specified"}:
        return None

    parts = s.split()
    if not parts:
        return None

    try:
        value = float(parts[0])
    except ValueError:
        return None

    unit = parts[1] if len(parts) > 1 else "years"
    unit = unit.rstrip("s")  # years -> year

    if unit == "year":
        years = value
    elif unit == "month":
        years = value / 12.0
    elif unit == "week":
        years = value / 52.0
    elif unit == "day":
        years = value / 365.0
    else:
        years = value  # default

    return int(years)


def split_criteria(raw_text: Optional[str]) -> List[Tuple[str, str]]:
    """
    Very simple parser that tries to split a big eligibilityCriteria block
    into ('inclusion'|'exclusion'|'other', bullet_text) rows.

    It looks for headings like 'Inclusion Criteria' / 'Exclusion Criteria'
    and treats bullet-like lines (-, *, •) as separate entries.
    """
    if not raw_text:
        return []

    lines = [l.strip() for l in raw_text.splitlines()]
    rows: List[Tuple[str, str]] = []

    current_type = "other"
    buffer: List[str] = []

    def flush_buffer():
        nonlocal buffer
        text = " ".join(buffer).strip()
        if text:
            rows.append((current_type, text))
        buffer = []

    for line in lines:
        lower = line.lower()

        if "inclusion criteria" in lower:
            flush_buffer()
            current_type = "inclusion"
            continue
        if "exclusion criteria" in lower:
            flush_buffer()
            current_type = "exclusion"
            continue

        # bullet-like lines start a new criterion
        if line.startswith(("-", "*", "•", "·", "•")):
            flush_buffer()
            # strip bullet symbols
            bullet_text = line.lstrip("-*•· ").strip()
            if bullet_text:
                rows.append((current_type, bullet_text))
        else:
            # continuation of previous bullet
            buffer.append(line)

    flush_buffer()
    return rows


def normalize_study(study: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[Tuple[str, str]]]:
    """
    Convert a raw 'study' record from the v2 API into:
      - trial_row dict
      - list of site_row dicts
      - list of (criteria_type, text) rows
    """
    protocol = study.get("protocolSection", {})

    id_mod = protocol.get("identificationModule", {})
    desc_mod = protocol.get("descriptionModule", {})
    status_mod = protocol.get("statusModule", {})
    design_mod = protocol.get("designModule", {})
    cond_mod = protocol.get("conditionsModule", {})
    int_mod = protocol.get("interventionsModule", {})
    elig_mod = protocol.get("eligibilityModule", {})
    loc_mod = protocol.get("contactsLocationsModule", {})

    nct_id = id_mod.get("nctId")

    # titles & descriptions
    brief_title = id_mod.get("briefTitle")
    official_title = id_mod.get("officialTitle")
    brief_summary = desc_mod.get("briefSummary")
    detailed_description = desc_mod.get("detailedDescription")

    # classification
    study_type = design_mod.get("studyType")
    phase_list = design_mod.get("phases") or []
    phase = ", ".join(phase_list) if isinstance(phase_list, list) else str(phase_list)

    overall_status = status_mod.get("overallStatus")

    # conditions & interventions
    conditions = cond_mod.get("conditions") or []
    
    conditions_cuis = []
    umls = get_umls()
    if umls and conditions:
        for c in conditions:
            conditions_cuis.extend(umls.extract_cuis(c))
    # Deduplicate
    conditions_cuis = list(set(conditions_cuis))

    interventions_raw = int_mod.get("interventions") or []
    interventions = []
    for intr in interventions_raw:
        name = intr.get("name")
        if name:
            interventions.append(name)

    # eligibility
    eligibility_criteria_raw = elig_mod.get("eligibilityCriteria")
    min_age_years = parse_age_to_years(elig_mod.get("minimumAge"))
    max_age_years = parse_age_to_years(elig_mod.get("maximumAge"))
    sex = elig_mod.get("sex")
    hv = elig_mod.get("healthyVolunteers")
    if isinstance(hv, bool):
        healthy_volunteers = hv
    elif isinstance(hv, str):
        healthy_volunteers = hv.lower() in {"yes", "true", "y"}
    else:
        healthy_volunteers = None

    # dates
    start_date = parse_iso_date(status_mod.get("startDateStruct"))
    primary_completion_date = parse_iso_date(status_mod.get("primaryCompletionDateStruct"))
    completion_date = parse_iso_date(status_mod.get("completionDateStruct"))
    last_updated = parse_iso_date(status_mod.get("lastUpdateSubmitDateStruct") or
                                  {"date": status_mod.get("lastUpdateSubmitDate")})

    # enrollment
    enrollment_info = design_mod.get("enrollmentInfo") or {}
    enrollment_count = enrollment_info.get("count")
    enrollment_type = (enrollment_info.get("type") or "").upper()
    enrollment_actual = None
    enrollment_target = None
    if isinstance(enrollment_count, (int, float)):
        if enrollment_type == "ACTUAL":
            enrollment_actual = int(enrollment_count)
        else:
            enrollment_target = int(enrollment_count)

    # sites
    sites_rows: List[Dict[str, Any]] = []
    locations = loc_mod.get("locations") or []
    for loc in locations:
        # facility sometimes nested, sometimes flat depending on API flavor
        facility_name = None
        facility = loc.get("facility")
        if isinstance(facility, dict):
            facility_name = facility.get("name")
        elif isinstance(facility, str):
            facility_name = facility
        else:
            facility_name = loc.get("facilityName")  # fallback

        address = loc.get("address") or {}
        city = address.get("city") or loc.get("city")
        state = address.get("state") or loc.get("state")
        country = address.get("country") or loc.get("country")
        postal_code = address.get("postalCode") or loc.get("postalCode") or loc.get("zip")

        recruitment_status = loc.get("status")

        sites_rows.append(
            {
                "facility_name": facility_name,
                "city": city,
                "state": state,
                "country": country,
                "zip": postal_code,
                "recruitment_status": recruitment_status,
            }
        )

    # criteria rows (type, text)
    criteria_rows = split_criteria(eligibility_criteria_raw)


    trial_row: Dict[str, Any] = {
        "nct_id": nct_id,
        "brief_title": brief_title,
        "official_title": official_title,
        "brief_summary": brief_summary,
        "detailed_description": detailed_description,
        "study_type": study_type,
        "phase": phase,
        "overall_status": overall_status,
        "conditions": conditions,
        "conditions_cuis": conditions_cuis,
        "interventions": interventions,
        "eligibility_criteria_raw": eligibility_criteria_raw,
        "min_age_years": min_age_years,
        "max_age_years": max_age_years,
        "sex": sex,
        "healthy_volunteers": healthy_volunteers,
        "start_date": start_date,
        "primary_completion_date": primary_completion_date,
        "completion_date": completion_date,
        "last_updated": last_updated,
        "enrollment_actual": enrollment_actual,
        "enrollment_target": enrollment_target,
        "source_json": study,
    }

    return trial_row, sites_rows, criteria_rows

def upsert_trial(
    cur,
    trial: Dict[str, Any],
    sites: List[Dict[str, Any]],
    criteria_rows: List[Tuple[str, str]],
) -> None:
    trial_sql = """
        INSERT INTO trials (
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
            eligibility_criteria_raw,
            min_age_years,
            max_age_years,
            sex,
            healthy_volunteers,
            start_date,
            primary_completion_date,
            completion_date,
            last_updated,
            enrollment_actual,
            enrollment_target,
            source_json
        ) VALUES (
            %(nct_id)s,
            %(brief_title)s,
            %(official_title)s,
            %(brief_summary)s,
            %(detailed_description)s,
            %(study_type)s,
            %(phase)s,
            %(overall_status)s,
            %(overall_status)s,
            %(conditions)s,
            %(conditions_cuis)s,
            %(interventions)s,
            %(eligibility_criteria_raw)s,
            %(min_age_years)s,
            %(max_age_years)s,
            %(sex)s,
            %(healthy_volunteers)s,
            %(start_date)s,
            %(primary_completion_date)s,
            %(completion_date)s,
            %(last_updated)s,
            %(enrollment_actual)s,
            %(enrollment_target)s,
            %(source_json)s
        )
        ON CONFLICT (nct_id) DO UPDATE SET
            brief_title = EXCLUDED.brief_title,
            official_title = EXCLUDED.official_title,
            brief_summary = EXCLUDED.brief_summary,
            detailed_description = EXCLUDED.detailed_description,
            study_type = EXCLUDED.study_type,
            phase = EXCLUDED.phase,
            overall_status = EXCLUDED.overall_status,
            conditions = EXCLUDED.conditions,
            conditions_cuis = EXCLUDED.conditions_cuis,
            interventions = EXCLUDED.interventions,
            eligibility_criteria_raw = EXCLUDED.eligibility_criteria_raw,
            min_age_years = EXCLUDED.min_age_years,
            max_age_years = EXCLUDED.max_age_years,
            sex = EXCLUDED.sex,
            healthy_volunteers = EXCLUDED.healthy_volunteers,
            start_date = EXCLUDED.start_date,
            primary_completion_date = EXCLUDED.primary_completion_date,
            completion_date = EXCLUDED.completion_date,
            last_updated = EXCLUDED.last_updated,
            enrollment_actual = EXCLUDED.enrollment_actual,
            enrollment_target = EXCLUDED.enrollment_target,
            source_json = EXCLUDED.source_json
        RETURNING id;
    """

    # copy + adapt source_json
    trial_for_db = trial.copy()
    if isinstance(trial_for_db.get("source_json"), dict):
        trial_for_db["source_json"] = Json(trial_for_db["source_json"])

    cur.execute(trial_sql, trial_for_db)
    trial_id = cur.fetchone()[0]

    # sites
    cur.execute("DELETE FROM sites WHERE trial_id = %s;", (trial_id,))
    for s in sites:
        cur.execute(
            """
            INSERT INTO sites (
                trial_id,
                facility_name,
                city,
                state,
                country,
                zip,
                recruitment_status,
                latitude,
                longitude
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, NULL, NULL);
            """,
            (
                trial_id,
                s.get("facility_name"),
                s.get("city"),
                s.get("state"),
                s.get("country"),
                s.get("zip"),
                s.get("recruitment_status"),
            ),
        )

    # criteria
    cur.execute("DELETE FROM criteria WHERE trial_id = %s;", (trial_id,))
    seq_no = 1
    for ctype, text in criteria_rows:
        cur.execute(
            """
            INSERT INTO criteria (trial_id, type, sequence_no, text)
            VALUES (%s, %s, %s, %s);
            """,
            (trial_id, ctype, seq_no, text),
        )
        seq_no += 1

def fetch_and_store(
    max_studies: int = 10_000,
    condition: Optional[str] = None,
    page_size: int = 100,
    max_retries: int = 5,
    retry_backoff_seconds: float = 5.0,
):
    """
    Robust, resumable ingestion from ClinicalTrials.gov v2 API into Postgres.

    - Uses ingestion_state table to remember last page_token & processed_count
    - Commits per page (safe for big runs)
    - Retries on network / HTTP errors with backoff
    - Can safely be re-run; it resumes where it left off
    """
    conn = psycopg2.connect(POSTGRES_DSN)
    conn.autocommit = False

    try:
        state = get_or_create_ingestion_state(conn)
        page_token = state["page_token"]
        already_processed = state["processed_count"] or 0

        print(f"Resuming from page_token={page_token!r}, already_processed={already_processed}")

        total_imported = already_processed

        while total_imported < max_studies:
            params = {"pageSize": page_size}
            if page_token:
                params["pageToken"] = page_token
            if condition:
                params["query.cond"] = condition

            # --- retry loop for this page ---
            attempt = 0
            while True:
                try:
                    resp = requests.get(API_BASE, params=params, timeout=30)
                    resp.raise_for_status()
                    data = resp.json()
                    break
                except Exception as e:
                    attempt += 1
                    if attempt > max_retries:
                        print(f"❌ Giving up after {max_retries} retries on page_token={page_token}: {e}")
                        raise
                    sleep_for = retry_backoff_seconds * attempt
                    print(f"⚠ Error fetching page (attempt {attempt}/{max_retries}): {e}. Sleeping {sleep_for}s...")
                    time.sleep(sleep_for)

            studies = data.get("studies") or []
            if not studies:
                print("No studies in response; stopping.")
                break

            page_count = 0

            # transact this page
            with conn:
                with conn.cursor() as cur:
                    for study in studies:
                        trial_row, sites_rows, criteria_rows = normalize_study(study)
                        if not trial_row.get("nct_id"):
                            continue

                        # Ensure source_json is Json-wrapped
                        if isinstance(trial_row.get("source_json"), dict):
                            trial_row["source_json"] = Json(trial_row["source_json"])

                        upsert_trial(cur, trial_row, sites_rows, criteria_rows)
                        total_imported += 1
                        page_count += 1

                        if total_imported >= max_studies:
                            break

                # update ingestion_state *after* successfully committing this page
                page_token = data.get("nextPageToken")
                update_ingestion_state(conn, page_token, page_count)

            print(
                f"Imported page with {page_count} studies. "
                f"total_imported={total_imported}, nextPageToken={page_token!r}"
            )

            if not page_token:
                print("No nextPageToken; reached end of API.")
                break

        print(f"✅ Full ingestion pass complete. Total imported/updated: {total_imported}")

    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Scrape ClinicalTrials.gov API v2 into Postgres (resumable).")
    parser.add_argument("--max-studies", type=int, default=50_000, help="Maximum number of studies to import in this run")
    parser.add_argument("--page-size", type=int, default=100, help="Page size for API calls (max ~100)")
    parser.add_argument("--condition", type=str, default=None, help="Optional condition filter (query.cond)")
    args = parser.parse_args()

    fetch_and_store(
        max_studies=args.max_studies,
        condition=args.condition,
        page_size=args.page_size,
    )


if __name__ == "__main__":
    main()

