CREATE INDEX IF NOT EXISTS ix_audit_events_created ON audit_events(created_at);
CREATE INDEX IF NOT EXISTS ix_audit_events_entity ON audit_events(entity_type,entity_id,created_at);
CREATE INDEX IF NOT EXISTS ix_device_events_device_created ON device_events(device_id,created_at);
CREATE INDEX IF NOT EXISTS ix_vending_tx_account_created ON vending_transactions(account_id,created_at);
INSERT OR REPLACE INTO system_meta(key,value) VALUES('schema_version','007');
