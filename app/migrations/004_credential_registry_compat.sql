CREATE TABLE IF NOT EXISTS credential_registry(
    credential_id TEXT PRIMARY KEY,
    credential_type TEXT NOT NULL,
    member_id TEXT NOT NULL REFERENCES identity_members(member_id),
    status TEXT NOT NULL DEFAULT 'active',
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
