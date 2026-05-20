CREATE TABLE IF NOT EXISTS event_ticks (
    id BIGSERIAL PRIMARY KEY,
    source TEXT NOT NULL,
    event_id TEXT NOT NULL,
    market TEXT NOT NULL,
    outcome TEXT NOT NULL,
    source_ts TIMESTAMPTZ,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    price NUMERIC,
    raw_prob NUMERIC,
    fair_prob NUMERIC,
    meta JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_event_ticks_event_time
ON event_ticks (event_id, ingested_at DESC);

CREATE INDEX IF NOT EXISTS idx_event_ticks_outcome_time
ON event_ticks (outcome, ingested_at DESC);
