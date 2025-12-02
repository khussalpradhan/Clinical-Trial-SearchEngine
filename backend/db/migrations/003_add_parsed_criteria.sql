-- Migration: Add parsed_criteria JSONB column to trials table
-- Date: 2025-12-02
-- Purpose: Cache pre-computed parser.parse() output to eliminate query-time parsing latency

ALTER TABLE trials ADD COLUMN IF NOT EXISTS parsed_criteria JSONB;

-- Create GIN index for efficient JSONB queries (future use)
CREATE INDEX IF NOT EXISTS idx_trials_parsed_criteria ON trials USING GIN (parsed_criteria);

-- Add comment
COMMENT ON COLUMN trials.parsed_criteria IS 'Pre-computed output of CriteriaParser.parse() stored as JSON for performance optimization';
