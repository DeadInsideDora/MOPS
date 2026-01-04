-- Alerts table for rule engine outputs
CREATE TABLE IF NOT EXISTS alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    rule_type TEXT NOT NULL CHECK (rule_type IN ('instant', 'persistent')),
    triggered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    payload JSONB NOT NULL,
    count INTEGER NOT NULL DEFAULT 1,
    severity INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS alerts_device_ts_idx ON alerts (device_id, triggered_at DESC);
CREATE INDEX IF NOT EXISTS alerts_rule_idx ON alerts (rule_id);
