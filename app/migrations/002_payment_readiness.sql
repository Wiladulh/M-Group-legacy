CREATE TABLE IF NOT EXISTS payment_providers(
    provider_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    payment_method TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'disabled',
    endpoint_base TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS payment_webhook_events(
    event_id TEXT PRIMARY KEY,
    provider_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    transaction_id TEXT,
    payload TEXT NOT NULL,
    processed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT OR IGNORE INTO system_meta(key,value) VALUES('payment_architecture_version','001');
