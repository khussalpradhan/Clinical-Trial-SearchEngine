CREATE TABLE IF NOT EXISTS trials (
    id                     SERIAL PRIMARY KEY,
    nct_id                 TEXT NOT NULL UNIQUE,

    -- Titles & descriptions
    brief_title            TEXT NOT NULL,
    official_title         TEXT,
    brief_summary          TEXT,
    detailed_description   TEXT,

    -- Trial classification
    study_type             TEXT,        -- e.g. "Interventional"
    phase                  TEXT,
    overall_status         TEXT,        -- e.g. "Recruiting"

    -- Condition & intervention
    conditions             TEXT[],      -- ['Lung Cancer', 'NSCLC']
    conditions_cuis        TEXT[],      -- ['C0024909', 'C0027051']
    interventions          TEXT[],      -- ['Osimertinib', 'Chemotherapy']

    -- Eligibility metadata
    eligibility_criteria_raw TEXT,      -- full block from API (raw text)
    min_age_years          INTEGER,     -- normalized to years if possible
    max_age_years          INTEGER,
    sex                    TEXT,        -- 'All' | 'Male' | 'Female'
    healthy_volunteers     BOOLEAN,

    -- Dates
    start_date             DATE,
    primary_completion_date DATE,
    completion_date        DATE,
    last_updated           TIMESTAMPTZ, -- lastUpdateSubmitDate normalized

    -- Scale
    enrollment_actual      INTEGER,
    enrollment_target      INTEGER,

    -- Raw payload from ClinicalTrials.gov (never remove this!)
    source_json            JSONB
);

CREATE INDEX IF NOT EXISTS idx_trials_phase
    ON trials (phase);

CREATE INDEX IF NOT EXISTS idx_trials_overall_status
    ON trials (overall_status);

CREATE INDEX IF NOT EXISTS idx_trials_study_type
    ON trials (study_type);

CREATE INDEX IF NOT EXISTS idx_trials_start_date
    ON trials (start_date);

CREATE INDEX IF NOT EXISTS idx_trials_primary_completion_date
    ON trials (primary_completion_date);

CREATE TABLE IF NOT EXISTS sites (
    id             SERIAL PRIMARY KEY,
    trial_id       INTEGER NOT NULL REFERENCES trials(id) ON DELETE CASCADE,
    facility_name  TEXT,
    city           TEXT,
    state          TEXT,
    country        TEXT,
    zip            TEXT,

    -- from ClinicalTrials.gov locations[].status
    recruitment_status TEXT,           -- e.g. 'Recruiting', 'Active, not recruiting'

    latitude       DOUBLE PRECISION,
    longitude      DOUBLE PRECISION
);

CREATE INDEX IF NOT EXISTS idx_sites_trial_id
    ON sites (trial_id);

CREATE INDEX IF NOT EXISTS idx_sites_country_state_city
    ON sites (country, state, city);

CREATE TABLE IF NOT EXISTS criteria (
    id          SERIAL PRIMARY KEY,
    trial_id    INTEGER NOT NULL REFERENCES trials(id) ON DELETE CASCADE,
    type        TEXT NOT NULL CHECK (type IN ('inclusion', 'exclusion', 'other')),
    sequence_no INTEGER,
    text        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_criteria_trial_id
    ON criteria (trial_id);

CREATE INDEX IF NOT EXISTS idx_criteria_type
    ON criteria (type);

CREATE TABLE IF NOT EXISTS ingestion_state (
    id              SERIAL PRIMARY KEY,
    job_name        TEXT NOT NULL UNIQUE,
    page_token      TEXT,
    processed_count INTEGER NOT NULL DEFAULT 0,
    last_run_at     TIMESTAMPTZ
);
